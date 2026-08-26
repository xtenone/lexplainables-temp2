import { proxy } from "../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ userid: string }> };

export async function POST(_req: Request, { params }: Params) {
  const { userid } = await params;
  return proxy(`/v1/admin/users/${pathSegment(userid)}/reset-password`, {
    method: "POST",
    admin: true,
  });
}
