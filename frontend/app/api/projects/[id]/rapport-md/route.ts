import { apiBaseUrl, authHeader } from "@/lib/config";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { id } = await params;
  const upstream = await fetch(
    `${apiBaseUrl()}/v1/projects/${pathSegment(id)}/rapport.md`,
    { headers: { ...authHeader() }, cache: "no-store" },
  );
  if (!upstream.ok) {
    return new Response(`Rapport (.md) niet beschikbaar (${upstream.status}).`, {
      status: upstream.status,
    });
  }
  // Bestandsnaam bestandssysteem-veilig maken: de slug kan een ':' bevatten (artikel 4:86),
  // wat op Windows ongeldig is en als rauw param `%3A` zou tonen.
  let slug = id;
  try {
    slug = decodeURIComponent(id);
  } catch {
    /* geen geldige percent-encoding */
  }
  const bestandsnaam = slug.replace(/[^a-zA-Z0-9._-]/g, "-");
  const text = await upstream.text();
  return new Response(text, {
    status: 200,
    headers: {
      "Content-Type": "text/markdown; charset=utf-8",
      "Content-Disposition": `attachment; filename="${bestandsnaam}.md"`,
    },
  });
}
