// BFF-route: een lopende run stoppen (graph-qa /v1/runs/{id}/cancel).
//
// Stoppen is nu een expliciete handeling in plaats van een dichtvallende socket. Dat onderscheid is
// het punt: wegklikken laat de beurt doorlopen, alleen deze knop beëindigt hem. Het antwoord is 202
// en geen 204 — de agent-nodes zijn synchroon, dus een lopende LLM-call maakt zichzelf af en de run
// eindigt pas op de eerstvolgende grens. Dit is een verzoek, geen feit.

import { graphQaAuthHeader, graphQaBaseUrl } from "@/lib/config";
import { logger } from "@/lib/logger";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function POST(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();

  const { id } = await params;
  try {
    const upstream = await fetch(
      `${graphQaBaseUrl()}/v1/runs/${encodeURIComponent(id)}/cancel`,
      {
        method: "POST",
        // Alleen je eigen beurt stoppen: graph-qa toetst deze header.
        headers: { ...graphQaAuthHeader(), "X-User-Id": userid },
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      },
    );
    const text = await upstream.text();
    return new Response(text || null, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    logger.warn("Run-cancel-proxy: onbereikbaar", { fout: (err as Error).message });
    return Response.json({ detail: `Agent onbereikbaar (${(err as Error).message})` }, { status: 502 });
  }
}
