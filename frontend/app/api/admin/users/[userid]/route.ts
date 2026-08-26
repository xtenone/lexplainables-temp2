import { proxy, readBody } from "../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ userid: string }> };

export async function PATCH(req: Request, { params }: Params) {
  const { userid } = await params;
  const body = await readBody(req);
  return proxy(`/v1/admin/users/${pathSegment(userid)}`, {
    method: "PATCH",
    body,
    admin: true,
    headers: { "Content-Type": "application/json" },
  });
}

export async function DELETE(_req: Request, { params }: Params) {
  const { userid } = await params;
  return proxy(`/v1/admin/users/${pathSegment(userid)}`, { method: "DELETE", admin: true });
}
