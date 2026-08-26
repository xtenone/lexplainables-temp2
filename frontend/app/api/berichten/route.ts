import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  // Alle query-params ongefilterd doorsturen. Een handmatige allowlist lijkt netter maar laat een
  // nieuwe param stil vallen tot iemand ook déze route bijwerkt; de api valideert ze toch al.
  const qs = new URL(req.url).search;
  return proxy(`/v1/berichten${qs}`, { headers: { "X-User-Id": userid } });
}
