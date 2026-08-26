import { proxy } from "../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ bwbId: string; artikel: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { bwbId, artikel } = await params;
  return proxy(`/v1/wetten/${pathSegment(bwbId)}/artikelen/${pathSegment(artikel)}`);
}
