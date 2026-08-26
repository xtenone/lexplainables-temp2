// BFF-route: artikeltekst uit de graaf via graph-qa (/v1/artikel), voor het workbench-documentpaneel.
// Eén bron: dezelfde tekst die de annotatie-agent als corpus gebruikt. Token gaat server-side mee.

import { graphQaAuthHeader, graphQaBaseUrl } from "@/lib/config";
import { logger } from "@/lib/logger";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();

  const { searchParams } = new URL(req.url);
  const bwbId = searchParams.get("bwb_id") ?? "";
  const artikel = searchParams.get("artikel") ?? "";
  const lid = searchParams.get("lid") ?? "";
  const url =
    `${graphQaBaseUrl()}/v1/artikel?bwb_id=${encodeURIComponent(bwbId)}&artikel=${encodeURIComponent(artikel)}` +
    (lid ? `&lid=${encodeURIComponent(lid)}` : "");
  try {
    // Eigen timeout: deze route loopt buiten `proxy()` om, en de graaf kan traag zijn zonder te
    // weigeren. Zonder dit blijft het artefact in "Openen…" staan.
    const upstream = await fetch(url, {
      headers: { ...graphQaAuthHeader() },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
    const text = await upstream.text();
    return new Response(text || null, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    logger.warn("Artikel-proxy: agent onbereikbaar", { fout: (err as Error).message });
    return Response.json({ detail: `Agent onbereikbaar (${(err as Error).message})` }, { status: 502 });
  }
}
