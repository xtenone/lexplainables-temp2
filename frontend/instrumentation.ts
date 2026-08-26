// Next.js instrumentation-hook: registreert OpenTelemetry (traces + metrics) via @vercel/otel.
// Gated op OTEL_EXPORTER_OTLP_ENDPOINT — zonder endpoint gebeurt er niets (geen overhead, geen
// dependency-lading). @vercel/otel instrumenteert automatisch de route handlers én uitgaande
// `fetch` (injecteert W3C-traceparent), zodat één trace de keten frontend → API → MCP/n8n omspant.
//
// Draait alleen in de nodejs-runtime (niet edge/middleware). Leest endpoint/protocol/service-name
// uit de standaard OTEL_*-env-vars.

export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  if (!process.env.OTEL_EXPORTER_OTLP_ENDPOINT) return;
  const { registerOTel } = await import("@vercel/otel");
  registerOTel({ serviceName: process.env.OTEL_SERVICE_NAME || "wetsanalyse-frontend" });
}
