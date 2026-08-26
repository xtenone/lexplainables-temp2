import { proxy } from "@/app/api/_lib/proxy";

export const dynamic = "force-dynamic";

export async function GET() {
  return proxy(`/v1/admin/profiles`, { admin: true });
}
