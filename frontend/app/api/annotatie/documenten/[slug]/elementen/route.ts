import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function PUT(req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}/elementen`, {
    method: "PUT",
    body: await req.text(),
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}

/** Eén eigen markering van de jurist. Aparte method, want dit is geen agent-ronde. */
export async function POST(req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}/elementen`, {
    method: "POST",
    body: await req.text(),
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}
