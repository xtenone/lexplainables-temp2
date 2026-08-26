import { proxy } from "../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params) {
  const { id } = await params;
  return proxy(`/v1/admin/projects/${pathSegment(id)}/llm-calls`, { admin: true });
}
