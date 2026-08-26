// Aggregate SSE-passthrough voor het live dashboard: open de upstream-stream van ALLE projecten
// van deze client server-side (met token) en pipe de text/event-stream ONGEWIJZIGD door. Net als
// de per-project events-route loopt dit bewust NIET via proxy() (die buffert) — bufferen breekt de
// live voortgang. De browser opent EventSource op deze same-origin route, zonder Authorization.

import { apiBaseUrl, authHeader } from "@/lib/config";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/v1/projects/events`, {
      headers: { ...authHeader(), Accept: "text/event-stream" },
      signal: req.signal, // client-disconnect propageren naar de upstream
      cache: "no-store",
    });
  } catch (err) {
    return new Response(`event: error\ndata: API onbereikbaar (${(err as Error).message})\n\n`, {
      status: 502,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  if (!upstream.ok || !upstream.body) {
    return new Response(`event: error\ndata: stream niet beschikbaar (${upstream.status})\n\n`, {
      status: upstream.status,
      headers: { "Content-Type": "text/event-stream" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
