import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string; id: string }> };

/** Verwijder een eigen markering. De api geeft 409 op een agent-voorstel; die status geven we
 *  ongewijzigd door, zodat de UI het verschil kan tonen. */
export async function DELETE(_req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug, id } = await params;
  return proxy(
    `/v1/annotatie/documenten/${pathSegment(slug)}/elementen/${pathSegment(id)}`,
    { method: "DELETE", headers: { "X-User-Id": userid } },
  );
}
