import { proxy, readBody } from "../../_lib/proxy";
import { geenSessie, sessionUserId } from "../../_lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const body = await readBody(req);
  return proxy(`/v1/auth/change-password`, {
    method: "POST",
    body,
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}
