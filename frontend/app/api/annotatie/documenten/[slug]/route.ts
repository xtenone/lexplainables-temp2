import { proxy } from "@/app/api/_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ slug: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}`);
}

export async function DELETE(_req: Request, { params }: Params) {
  const { slug } = await params;
  return proxy(`/v1/annotatie/documenten/${pathSegment(slug)}`, { method: "DELETE" });
}
