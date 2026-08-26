import { apiBaseUrl, authHeader } from "@/lib/config";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

// Eén gecombineerd Markdown-document: het wetsanalyse-rapport gevolgd door de
// RegelSpraak-formalisering (indien aanwezig). Spiegelt rapport-md/route.ts qua token-injectie
// en bestandsnaam-sanitatie; de RegelSpraak-fetch is optioneel (state `klaar` heeft hem nog niet).
export async function GET(_req: Request, { params }: Params) {
  const { id } = await params;
  const seg = pathSegment(id);
  const headers = { ...authHeader() };

  const rapport = await fetch(`${apiBaseUrl()}/v1/projects/${seg}/rapport.md`, {
    headers,
    cache: "no-store",
  });
  if (!rapport.ok) {
    return new Response(`Rapport (.md) niet beschikbaar (${rapport.status}).`, {
      status: rapport.status,
    });
  }
  let doc = await rapport.text();

  // RegelSpraak optioneel meenemen: ontbreekt hij (nog niet geformaliseerd), dan blijft het
  // bij het rapportdeel — geen fout.
  const regelspraak = await fetch(`${apiBaseUrl()}/v1/projects/${seg}/regelspraak.md`, {
    headers,
    cache: "no-store",
  });
  if (regelspraak.ok) {
    const rs = await regelspraak.text();
    doc += `\n\n---\n\n# RegelSpraak-formalisering\n\n${rs}`;
  }

  // Bestandsnaam bestandssysteem-veilig maken (de slug kan een ':' bevatten, bv. artikel 4:86).
  let slug = id;
  try {
    slug = decodeURIComponent(id);
  } catch {
    /* geen geldige percent-encoding */
  }
  const bestandsnaam = slug.replace(/[^a-zA-Z0-9._-]/g, "-");
  return new Response(doc, {
    status: 200,
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="${bestandsnaam}-volledig.md"`,
    },
  });
}
