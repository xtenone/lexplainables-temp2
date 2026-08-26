import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function GET() {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  return proxy(`/v1/auth/me`, { headers: { "X-User-Id": userid } });
}
