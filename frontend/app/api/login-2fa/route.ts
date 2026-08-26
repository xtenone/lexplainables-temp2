// Publieke stap B van de login (het aparte /login/2fa-scherm): verifieert de TOTP-code met het
// login-ticket uit stap A (httpOnly cookie) — het wachtwoord is hier dus niet nodig. Bij "30 dagen
// onthouden" zet de route een httpOnly trusted-device-cookie. Zet géén sessie; dat doet de
// daaropvolgende signIn (die het login-ticket server-side in authorize opnieuw gebruikt).
import { postAuthVerify } from "@/lib/server";
import {
  getLoginTicketCookie,
  setTrustedDeviceCookie,
} from "@/lib/authCookies";

export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  const { userid, totp, remember } = (await req.json().catch(() => ({}))) as {
    userid?: string;
    totp?: string;
    remember?: boolean;
  };
  const ticket = (await getLoginTicketCookie()) ?? null;
  if (!ticket) {
    // Geen (geldig) ticket meer → stap A opnieuw doen.
    return Response.json({ ok: false, code: "invalid" }, { status: 401 });
  }

  const { status, body } = await postAuthVerify({
    userid: userid ?? "",
    ticket,
    totp: totp ?? null,
    remember: remember === true,
  });

  if (body.ok && body.trusted_token) {
    // "Dit apparaat 30 dagen onthouden": sla de 2FA-prompt voortaan over op deze browser.
    await setTrustedDeviceCookie(body.trusted_token);
  }
  // Laat het login-ticket staan — de aansluitende signIn heeft het nog nodig in authorize; het
  // vervalt vanzelf via zijn korte Fernet-TTL.

  return Response.json(
    { ok: body.ok, code: body.code, userid: userid ?? "" },
    { status: status === 429 ? 429 : 200 },
  );
}
