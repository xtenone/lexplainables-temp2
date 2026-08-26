import { proxy } from "@/app/api/_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string; id: string }> };

export async function POST(req: Request, { params }: Params) {
  const { slug, id } = await params;
  return proxy(
    `/v1/annotatie/documenten/${pathSegment(slug)}/elementen/${pathSegment(id)}/beslissing`,
    { method: "POST", body: await req.text(), headers: { "Content-Type": "application/json" } },
  );
}
