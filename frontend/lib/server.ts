// Server-side helpers voor Server Components: praten rechtstreeks (server→server) met de API,
// zodat de initiële render geen extra self-fetch via de BFF-route nodig heeft. Het token komt
// uit lib/config (server-only). NOOIT importeren vanuit een Client Component.

import "server-only";
import { apiBaseUrl, authHeader } from "./config";
import { logger } from "./logger";
import { pathSegment } from "./url";
import type { Job, JobSummary, Rapport } from "./types";

async function serverGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBaseUrl()}${path}`, {
    headers: { ...authHeader() },
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    logger.warn("Server-fetch niet-ok", { http_path: path, http_status: res.status });
    const err = new Error(`API ${res.status} op ${path}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as T;
}

export function getProjectsServer(limit = 50, offset = 0): Promise<JobSummary[]> {
  return serverGet<JobSummary[]>(`/v1/projects?limit=${limit}&offset=${offset}`);
}

export function getProjectServer(id: string): Promise<Job> {
  return serverGet<Job>(`/v1/projects/${pathSegment(id)}`);
}

export function getRapportServer(id: string): Promise<Rapport> {
  return serverGet<Rapport>(`/v1/projects/${pathSegment(id)}/rapport`);
}

// --- Auth (server→server; aangeroepen door auth.ts en de login/setup-pagina's) ---------------

export interface VerifyResult {
  ok: boolean;
  code: string; // "" | "invalid" | "totp_required" | "rate"
  userid: string;
  email: string;
  role: "beheerder" | "analist" | "";
  // Server→server-only (via httpOnly cookies gezet door de BFF; nooit naar de browser-JS).
  ticket?: string | null; // bij totp_required: bewijs voor het aparte 2FA-scherm
  trusted_token?: string | null; // bij ok + remember: 30-daags "dit apparaat onthouden"-token
}

/** Alternatieve bewijzen naast het wachtwoord, uit de httpOnly cookies (server-side gelezen). */
export interface VerifyOpts {
  ticket?: string | null;
  trusted_token?: string | null;
  remember?: boolean;
}

/** Lage-niveau POST naar `/v1/auth/verify` — geeft de VOLLEDIGE respons (incl. ticket/trusted_token)
 *  zodat de BFF-login-routes de cookies kunnen zetten. Server→server; nooit vanuit een client. */
export async function postAuthVerify(
  payload: Record<string, unknown>,
): Promise<{ status: number; body: VerifyResult }> {
  const res = await fetch(`${apiBaseUrl()}/v1/auth/verify`, {
    method: "POST",
    headers: { ...authHeader(), "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (res.status === 429) {
    return { status: 429, body: { ok: false, code: "rate", userid: "", email: "", role: "" } };
  }
  const body = (await res
    .json()
    .catch(() => ({ ok: false, code: "invalid", userid: "", email: "", role: "" }))) as VerifyResult;
  return { status: res.status, body };
}

/** Valideer inloggegevens (op userid) bij de API. Gebruikt door de Auth.js Credentials-provider;
 *  `opts` draagt de httpOnly-cookie-bewijzen (login-ticket / trusted-device) die authorize meestuurt. */
export async function verifyCredentials(
  userid: string,
  password: string,
  totp?: string,
  opts: VerifyOpts = {},
): Promise<VerifyResult> {
  const { body } = await postAuthVerify({
    userid,
    password,
    totp: totp ?? null,
    ticket: opts.ticket ?? null,
    trusted_token: opts.trusted_token ?? null,
    remember: opts.remember ?? false,
  });
  return body;
}

/** Actuele accountstatus voor de periodieke sessie-herverificatie (jwt-callback in auth.ts). */
export type AccountStatus =
  | { status: "actief"; role: "beheerder" | "analist"; email: string }
  | { status: "ingetrokken" } // 401: account inactief of verwijderd → sessie invalideren
  | { status: "onbekend" }; // API tijdelijk onbereikbaar → sessie laten staan (maxAge begrenst)

/** Raadpleeg `/v1/auth/me` (identiteit via de vertrouwde X-User-Id, zoals de account-routes). */
export async function getAccountStatus(userid: string): Promise<AccountStatus> {
  try {
    const res = await fetch(`${apiBaseUrl()}/v1/auth/me`, {
      headers: { ...authHeader(), "X-User-Id": userid },
      cache: "no-store",
    });
    if (res.status === 401) return { status: "ingetrokken" };
    if (!res.ok) return { status: "onbekend" };
    const me = (await res.json()) as { role: "beheerder" | "analist"; email: string };
    return { status: "actief", role: me.role, email: me.email };
  } catch {
    return { status: "onbekend" };
  }
}

/** Is er nog geen enkel account? Dan staat de eenmalige registratie open. */
export async function getSetupStatus(): Promise<{ needs_setup: boolean }> {
  try {
    return await serverGet<{ needs_setup: boolean }>(`/v1/auth/setup-status`);
  } catch {
    // API onbereikbaar: ga uit van "geen setup nodig" zodat we niet onbedoeld registratie openen.
    return { needs_setup: false };
  }
}
