// Lokale liveness voor de Docker HEALTHCHECK. Test óók of de upstream-API bereikbaar is,
// maar faalt niet hard daarop — de frontend zelf leeft zolang dit antwoordt.

import { apiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET() {
  let api = "onbekend";
  try {
    const res = await fetch(`${apiBaseUrl()}/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    api = res.ok ? "ok" : `status-${res.status}`;
  } catch {
    api = "onbereikbaar";
  }
  return Response.json({ status: "ok", api });
}
