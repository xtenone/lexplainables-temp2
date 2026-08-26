import { proxy } from "../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function POST(_req: Request, { params }: Params) {
  const { id } = await params;
  return proxy(`/v1/projects/${pathSegment(id)}/retry`, { method: "POST" });
}
