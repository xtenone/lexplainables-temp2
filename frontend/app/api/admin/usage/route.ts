import { proxy } from "../../_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const qs = new URL(req.url).search;
  return proxy(`/v1/admin/usage${qs}`, { admin: true });
}
