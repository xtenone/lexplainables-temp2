// Server-side gestructureerde JSON-logging voor de BFF, gespiegeld aan de MCP-logger
// (tools/wettenbank-mcp/src/logger.ts): één regel JSON per gebeurtenis naar stdout, met
// `ts/niveau/categorie/bericht/…velden`, secret-redactie en — indien een OTel-span actief is —
// `trace_id`/`span_id`. NOOIT importeren vanuit een Client Component (dit is server-only).
//
// AVG/dataminimalisatie: tokens, secrets en verzoek-/antwoordinhoud worden nooit gelogd — alleen
// metadata (status, duur, lengtes, paden). Faalt nooit hard: logging mag een request niet breken.

import "server-only";
import { trace } from "@opentelemetry/api";

export type LogNiveau = "debug" | "info" | "warn" | "error";
export type LogCategorie = "functioneel" | "audit" | "security";
export type LogVelden = Record<string, unknown>;

const NIVEAUS: Record<LogNiveau, number> = { debug: 10, info: 20, warn: 30, error: 40 };

function drempelNiveau(): number {
  const env = (process.env.LOG_LEVEL ?? "info").toLowerCase();
  return NIVEAUS[env as LogNiveau] ?? NIVEAUS.info;
}

/** Veldnamen die nooit in een logregel mogen verschijnen (mirror van GEHEIME_VELDEN in de MCP). */
const GEHEIME_VELDEN = new Set([
  "authorization",
  "token",
  "bearer",
  "secret",
  "chat_secret",
  "password",
  "api_key",
  "apikey",
]);

function saneer(velden: LogVelden): LogVelden {
  const schoon: LogVelden = {};
  for (const [k, v] of Object.entries(velden)) {
    if (GEHEIME_VELDEN.has(k.toLowerCase())) continue;
    if (v === undefined || v === null) continue;
    schoon[k] = v;
  }
  return schoon;
}

/** `{trace_id, span_id}` van de actieve OTel-span, of leeg als er geen (geldige) span is. */
function traceContext(): LogVelden {
  try {
    const span = trace.getActiveSpan();
    if (!span) return {};
    const ctx = span.spanContext();
    if (!ctx || !ctx.traceId || ctx.traceId === "00000000000000000000000000000000") return {};
    return { trace_id: ctx.traceId, span_id: ctx.spanId };
  } catch {
    return {};
  }
}

/** Schrijf één gestructureerde logregel naar stdout. Faalt nooit hard. */
export function log(
  niveau: LogNiveau,
  categorie: LogCategorie,
  bericht: string,
  velden: LogVelden = {},
): void {
  if (NIVEAUS[niveau] < drempelNiveau()) return;
  try {
    const regel = {
      ts: new Date().toISOString(), // UTC
      niveau,
      categorie,
      bericht,
      ...traceContext(),
      ...saneer(velden),
    };
    process.stdout.write(JSON.stringify(regel) + "\n");
  } catch {
    /* nooit laten omvallen op een logfout */
  }
}

/** Gemakshelpers met categorie `functioneel` (de overgrote meerderheid). */
export const logger = {
  debug: (bericht: string, velden?: LogVelden) => log("debug", "functioneel", bericht, velden),
  info: (bericht: string, velden?: LogVelden) => log("info", "functioneel", bericht, velden),
  warn: (bericht: string, velden?: LogVelden) => log("warn", "functioneel", bericht, velden),
  error: (bericht: string, velden?: LogVelden) => log("error", "functioneel", bericht, velden),
};
