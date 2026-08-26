// SSE-passthrough: open de upstream-stream server-side (met token) en pipe de
// text/event-stream ONGEWIJZIGD door. De browser opent EventSource op deze same-origin
// route en heeft dus geen Authorization-header nodig.

import { apiBaseUrl, authHeader } from "@/lib/config";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(req: Request, { params }: Params) {
  const { id } = await params;
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/v1/projects/${pathSegment(id)}/events`, {
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
