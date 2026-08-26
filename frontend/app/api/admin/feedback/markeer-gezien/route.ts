import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const body = await req.text();
  return proxy("/v1/admin/feedback/markeer-gezien", {
    method: "POST",
    body: body || undefined,
    headers: {
      "X-User-Id": userid,
      ...(body ? { "Content-Type": "application/json" } : {}),
    },
    admin: true,
  });
}
