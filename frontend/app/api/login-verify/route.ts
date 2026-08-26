// Publieke stap A van de login: vraagt de API of userid+wachtwoord kloppen en of 2FA nodig is.
// - Stuurt een eventuele trusted-device-cookie mee: een vertrouwd apparaat slaat 2FA over (code "ok").
// - Bij "totp_required" zet deze route een httpOnly login-ticket-cookie en stuurt de gebruiker
//   (client-side) door naar /login/2fa; het ticket draagt de al-geverifieerde identiteit, zodat het
//   wachtwoord daar niet nodig is.
// Zet géén sessie — dat doet Auth.js (signIn) pas ná een geslaagde check. De API rate-limit't /verify.
import { postAuthVerify } from "@/lib/server";
import {
  getTrustedDeviceCookie,
  setLoginTicketCookie,
} from "@/lib/authCookies";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { userid, password } = (await req.json().catch(() => ({}))) as {
    userid?: string;
    password?: string;
  };
  const trusted_token = (await getTrustedDeviceCookie()) ?? null;
  const { status, body } = await postAuthVerify({
    userid: userid ?? "",
    password: password ?? "",
    trusted_token,
  });

  if (body.code === "totp_required" && body.ticket) {
    await setLoginTicketCookie(body.ticket);
  }

  // Naar de client alleen het niet-gevoelige deel; ticket/trusted_token blijven in de httpOnly cookie.
  return Response.json(
    { ok: body.ok, code: body.code, userid: userid ?? "", email: body.email, role: body.role },
    { status: status === 429 ? 429 : 200 },
  );
}
