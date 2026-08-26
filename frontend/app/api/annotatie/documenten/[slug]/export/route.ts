// Export van één annotatiedocument (pdf|csv|json). De api bouwt het bestand; deze route stuurt
// alleen door — inclusief `Content-Disposition`, anders landt de download naamloos in de browser.
//
// De wettekst zit NIET in de api (de graaf is de bron), dus de werkplek stuurt de leden mee in de
// body. Zonder leden laat het rapport dat blok gewoon weg; niets wordt gereconstrueerd.

import { proxy, readBody } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

const FORMATEN = new Set(["pdf", "csv", "json"]);

export async function POST(req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;

  // De queryparam expliciet doorgeven: een proxyroute die hem laat vallen faalt stil (je krijgt
  // dan altijd het default-formaat terug).
  const formaat = new URL(req.url).searchParams.get("formaat") ?? "pdf";
  if (!FORMATEN.has(formaat)) {
    return Response.json({ detail: `Onbekend exportformaat: ${formaat}` }, { status: 422 });
  }

  return proxy(
    `/v1/annotatie/documenten/${pathSegment(slug)}/export?formaat=${encodeURIComponent(formaat)}`,
    {
      method: "POST",
      body: await readBody(req),
      headers: { "Content-Type": "application/json", "X-User-Id": userid },
      // Een PDF met veel elementen kost meer dan een gewone call, maar blijft ver onder de default.
      timeoutMs: 60_000,
    },
  );
}
