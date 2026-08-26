import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function POST() {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  return proxy("/v1/berichten/lees-alles", {
    method: "POST",
    headers: { "X-User-Id": userid },
  });
}
