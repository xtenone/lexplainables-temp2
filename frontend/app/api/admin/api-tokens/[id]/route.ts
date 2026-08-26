import { proxy } from "../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function DELETE(_req: Request, { params }: Params) {
  const { id } = await params;
  return proxy(`/v1/admin/api-tokens/${pathSegment(id)}`, { method: "DELETE", admin: true });
}
