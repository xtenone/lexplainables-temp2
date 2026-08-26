import { proxy } from "../../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string; act: string; n: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { id, act, n } = await params;
  return proxy(
    `/v1/projects/${pathSegment(id)}/ronde/${pathSegment(act)}/${pathSegment(n)}`,
  );
}
