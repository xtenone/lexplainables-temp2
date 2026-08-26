import { proxy } from "../../../../_lib/proxy";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ name: string }> };

export async function POST(_req: Request, { params }: Params) {
  const { name } = await params;
  return proxy(`/v1/admin/profiles/${pathSegment(name)}/test`, {
    method: "POST",
    admin: true,
  });
}
