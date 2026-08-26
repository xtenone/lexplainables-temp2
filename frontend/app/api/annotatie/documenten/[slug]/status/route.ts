// Afronden / heropenen van een annotatiedocument. Dunne doorgifte: de api bezit de regels (welke
// toestanden mogen, 404 op andermans slug) en die status komt hier ongewijzigd doorheen.

import { proxy, readBody } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function POST(req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}/status`, {
    method: "POST",
    body: await readBody(req),
    headers: { "Content-Type": "application/json", "X-User-Id": userid },
  });
}
