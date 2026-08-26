// Server-side configuratie. Mag NOOIT vanuit een Client Component geïmporteerd worden:
// hier zit het API-token. Alleen Route Handlers en Server Components gebruiken dit.

import { readFileSync } from "node:fs";

let cachedToken: string | null = null;
let cachedAdminToken: string | null = null;

export function apiBaseUrl(): string {
  return (process.env.API_BASE_URL || "http://wetsanalyse-api:3000").replace(/\/+$/, "");
}

/** Bearer-token uit API_TOKEN_FILE (voorrang) of API_TOKEN. Gecached na eerste lees. */
export function apiToken(): string {
  if (cachedToken !== null) return cachedToken;
  const file = process.env.API_TOKEN_FILE;
  if (file) {
    try {
      cachedToken = readFileSync(file, "utf8").trim();
      return cachedToken;
    } catch (err) {
      throw new Error(`Kan API_TOKEN_FILE niet lezen (${file}): ${(err as Error).message}`);
    }
  }
  cachedToken = (process.env.API_TOKEN || "").trim();
  return cachedToken;
}

export function authHeader(): Record<string, string> {
  const token = apiToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Apart admin-bearer-token (voor /v1/admin/*) uit ADMIN_API_TOKEN_FILE (voorrang) of ADMIN_API_TOKEN. */
export function adminToken(): string {
  if (cachedAdminToken !== null) return cachedAdminToken;
  const file = process.env.ADMIN_API_TOKEN_FILE;
  if (file) {
    try {
      cachedAdminToken = readFileSync(file, "utf8").trim();
      return cachedAdminToken;
    } catch (err) {
      throw new Error(`Kan ADMIN_API_TOKEN_FILE niet lezen (${file}): ${(err as Error).message}`);
    }
  }
  cachedAdminToken = (process.env.ADMIN_API_TOKEN || "").trim();
  return cachedAdminToken;
}

export function adminAuthHeader(): Record<string, string> {
  const token = adminToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// --- graph-qa (annotatie-agent) ---------------------------------------------
// De workbench streamt annotatie-voorstellen rechtstreeks van graph-qa (SSE), náást de api voor
// state. graph-qa draait intern (homeinfra_internal) en is token-gated (QA_API_TOKEN).

let cachedGraphQaToken: string | null = null;

export function graphQaBaseUrl(): string {
  return (process.env.GRAPH_QA_URL || "http://graph-qa:8080").replace(/\/+$/, "");
}

/** graph-qa-token uit GRAPH_QA_TOKEN_FILE (voorrang) of GRAPH_QA_TOKEN. Gecached na eerste lees. */
export function graphQaToken(): string {
  if (cachedGraphQaToken !== null) return cachedGraphQaToken;
  const file = process.env.GRAPH_QA_TOKEN_FILE;
  if (file) {
    try {
      cachedGraphQaToken = readFileSync(file, "utf8").trim();
      return cachedGraphQaToken;
    } catch (err) {
      throw new Error(`Kan GRAPH_QA_TOKEN_FILE niet lezen (${file}): ${(err as Error).message}`);
    }
  }
  cachedGraphQaToken = (process.env.GRAPH_QA_TOKEN || "").trim();
  return cachedGraphQaToken;
}

export function graphQaAuthHeader(): Record<string, string> {
  const token = graphQaToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
