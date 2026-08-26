import { proxy, readBody } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const body = await readBody(req);
  return proxy(`/v1/auth/2fa/disable`, {
    method: "POST",
    body,
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}
