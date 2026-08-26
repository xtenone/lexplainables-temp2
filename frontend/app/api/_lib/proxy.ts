// Kern van de BFF: forward een request naar de upstream-API met server-side token-injectie,
// en geef de upstream-status + body ONGEWIJZIGD terug (incl. 401/404/409/429/503 en de
// Retry-After / Location headers), zodat de client correcte foutafhandeling houdt.

import { adminAuthHeader, apiBaseUrl, authHeader } from "@/lib/config";
import { logger } from "@/lib/logger";

// `content-disposition` hoort erbij zodra een endpoint een bestand teruggeeft (de export):
// zonder die header opent de browser de download als een naamloze blob.
const PASS_THROUGH_HEADERS = ["retry-after", "location", "content-type", "content-disposition"];

/** Hoe lang de BFF op de upstream wacht.
 *
 *  Node's `fetch` kent geen standaardtimeout: een upstream die de verbinding wél accepteert maar niet
 *  antwoordt, houdt zowel deze request als de browser onbeperkt vast. De UI blijft dan in zijn
 *  laadstand hangen — zonder de foutmelding en de "opnieuw proberen"-knop die er speciaal voor zijn.
 *  Dertig seconden is ruim voor elke gewone API-call; wie langer nodig heeft (een modeltest doet een
 *  echte LLM-aanroep) zet `timeoutMs` zelf hoger. */
const STANDAARD_TIMEOUT_MS = 30_000;

interface ProxyInit {
  method?: string;
  /** Rauwe request-body (al als string/Buffer); voor POST met JSON. */
  body?: BodyInit;
  /** Extra headers naar de upstream (bv. Content-Type). */
  headers?: Record<string, string>;
  /** Injecteer het admin-token i.p.v. het gewone client-token (voor /v1/admin/*). */
  admin?: boolean;
  /** Afwijkende wachttijd op de upstream (ms). Default `STANDAARD_TIMEOUT_MS`. */
  timeoutMs?: number;
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
  const timeoutMs = init.timeoutMs ?? STANDAARD_TIMEOUT_MS;
  const start = performance.now();
  let upstream: Response;
  try {
    upstream = await fetch(upstreamUrl, {
      method,
      headers: { ...authHeaders, ...(init.headers ?? {}) },
      body: init.body,
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (err) {
    // Een timeout is iets anders dan een onbereikbare API, en de gebruiker heeft aan "the operation
    // was aborted" niets. 504 zodat de client het als een tijdelijke hapering kan behandelen.
    const verlopen = (err as Error).name === "TimeoutError";
    logger.error(verlopen ? "BFF-proxy: API antwoordde niet op tijd" : "BFF-proxy: API onbereikbaar", {
      http_method: method,
      http_path: path,
      fout: (err as Error).message,
      timeout_ms: verlopen ? timeoutMs : undefined,
    });
    const wacht = timeoutMs >= 1000 ? `${Math.round(timeoutMs / 1000)} seconden` : `${timeoutMs} ms`;
    return Response.json(
      {
        detail: verlopen
          ? `De API antwoordde niet binnen ${wacht}.`
          : `API onbereikbaar: ${(err as Error).message}`,
      },
      { status: verlopen ? 504 : 502 },
    );
  }
  logger.info("BFF-proxy", {
    http_method: method,
    http_path: path,
    http_status: upstream.status,
    duur_ms: Math.round(performance.now() - start),
  });

  // Stream de body door en kopieer relevante headers (status + headers ongewijzigd).
  const headers = new Headers();
  for (const h of PASS_THROUGH_HEADERS) {
    const v = upstream.headers.get(h);
    if (v) headers.set(h, v);
  }
  const buf = await upstream.arrayBuffer();
  return new Response(buf.byteLength ? buf : null, {
    status: upstream.status,
    headers,
  });
}

/** Helper om de JSON-body van een inkomend request door te sturen. */
export async function readBody(req: Request): Promise<string> {
  return req.text();
}
