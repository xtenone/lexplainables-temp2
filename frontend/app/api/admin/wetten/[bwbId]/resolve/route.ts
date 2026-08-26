import { proxy } from "../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ bwbId: string }> };

export async function POST(_req: Request, { params }: Params) {
  const { bwbId } = await params;
  return proxy(`/v1/admin/wetten/${pathSegment(bwbId)}/resolve`, {
    method: "POST",
    admin: true,
  });
}
