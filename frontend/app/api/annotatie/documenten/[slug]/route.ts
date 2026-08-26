import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function GET(_req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}`, { headers: { "X-User-Id": userid } });
}

export async function DELETE(_req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}`, {
    method: "DELETE",
    headers: { "X-User-Id": userid },
  });
}
