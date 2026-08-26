import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";

export const dynamic = "force-dynamic";

// Gesprekken zijn per-gebruiker gescopet: de BFF geeft de ingelogde identiteit door als vertrouwde
// X-User-Id-header (uit de sessie, nooit uit browser-input), net als de account-routes.

export async function GET(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const qs = new URL(req.url).search;
  return proxy(`/v1/gesprekken${qs}`, { headers: { "X-User-Id": userid } });
}

export async function POST(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  return proxy(`/v1/gesprekken`, {
    method: "POST",
    body: await req.text(),
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}
