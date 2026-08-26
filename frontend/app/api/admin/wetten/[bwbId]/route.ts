import { proxy, readBody } from "../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ bwbId: string }> };

export async function PUT(req: Request, { params }: Params) {
  const { bwbId } = await params;
  const body = await readBody(req);
  return proxy(`/v1/admin/wetten/${pathSegment(bwbId)}`, {
    method: "PUT",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE(_req: Request, { params }: Params) {
  const { bwbId } = await params;
  return proxy(`/v1/admin/wetten/${pathSegment(bwbId)}`, {
    method: "DELETE",
    admin: true,
  });
}
