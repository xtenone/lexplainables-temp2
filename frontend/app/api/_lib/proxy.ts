// Kern van de BFF: forward een request naar de upstream-API met server-side token-injectie,
// en geef de upstream-status + body ONGEWIJZIGD terug (incl. 401/404/409/429/503 en de
// Retry-After / Location headers), zodat de client correcte foutafhandeling houdt.

import { adminAuthHeader, apiBaseUrl, authHeader } from "@/lib/config";
import { logger } from "@/lib/logger";

const PASS_THROUGH_HEADERS = ["retry-after", "location", "content-type"];

interface ProxyInit {
  method?: string;
  /** Rauwe request-body (al als string/Buffer); voor POST met JSON. */
  body?: BodyInit;
  /** Extra headers naar de upstream (bv. Content-Type). */
  headers?: Record<string, string>;
  /** Injecteer het admin-token i.p.v. het gewone client-token (voor /v1/admin/*). */
  admin?: boolean;
}

export async function proxy(path: string, init: ProxyInit = {}): Promise<Response> {
  // Defense-in-depth: de middleware gate't /api/admin al op rol, maar een admin-proxy dwingt de
  // beheerder-rol hier server-side nóg eens af — één matcher-/callback-regressie opent dan niet
  // meteen alle admin-endpoints. Onafhankelijk van, en náást, de middleware.
  if (init.admin) {
    // Dynamische import: houdt de module vrij van de node-only auth-stack (en de unit-test licht);
    // alleen een echte admin-proxy laadt 'm.
    const { auth } = await import("@/auth");
    const session = await auth();
    if ((session?.user as { role?: string } | undefined)?.role !== "beheerder") {
      return Response.json({ detail: "Alleen voor beheerders." }, { status: 403 });
    }
  }
  const upstreamUrl = `${apiBaseUrl()}${path}`;
  const authHeaders = init.admin ? adminAuthHeader() : authHeader();
  const method = init.method ?? "GET";
  const start = performance.now();
  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method,
      headers: { ...authHeaders, ...(init.headers ?? {}) },
      body: init.body,
      cache: "no-store",
    });
  } catch (err) {
    logger.error("BFF-proxy: API onbereikbaar", {
      http_method: method,
      http_path: path,
      fout: (err as Error).message,
    });
    return Response.json(
      { detail: `API onbereikbaar: ${(err as Error).message}` },
      { status: 502 },
    );
  }
  logger.info("BFF-proxy", {
    http_method: method,
    http_path: path,
    http_status: upstream.status,
    duur_ms: Math.round(performance.now() - start),
  });

  // Stream de body door en kopieer relevante headers.
  const headers = new Headers();
  for (const h of PASS_THROUGH_HEADERS) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, h === "location" ? rewriteLocation(v) : v);
  }
  const buf = await upstream.arrayBuffer();
  return new Response(buf.byteLength ? buf : null, {
    status: upstream.status,
    headers,
  });
}

/** Vertaal een upstream Location (/v1/projects/{id}) naar de eigen BFF-route. */
export function rewriteLocation(loc: string): string {
  return loc.replace(/^.*\/v1\/projects\//, "/api/projects/");
}

/** Helper om de JSON-body van een inkomend request door te sturen. */
export async function readBody(req: Request): Promise<string> {
  return req.text();
}
