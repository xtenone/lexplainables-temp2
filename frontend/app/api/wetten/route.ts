import { proxy } from "../_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return proxy(`/v1/wetten`);
}
