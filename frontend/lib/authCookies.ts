// Server-only helpers voor de stateless cookies naast de Auth.js-sessiecookie:
//  - login-ticket: kortlevend (5 min) bewijs "wachtwoord geverifieerd", zodat het aparte
//    /login/2fa-scherm het wachtwoord niet hoeft vast te houden;
//  - trusted-device: 30-daags token dat op dit apparaat de 2FA-prompt overslaat;
//  - disclaimer: markeert dat de PoC-disclaimer deze sessie is gezien (zie lib/disclaimer.ts).
// De eerste twee zijn Fernet-tokens die de API uitgeeft/valideert; hier alleen als httpOnly cookie
// beheerd. Cookie-flags spiegelen auth.config.ts (httpOnly, sameSite=lax, secure + __Secure- in prod).

import "server-only";
import { cookies } from "next/headers";
import { DISCLAIMER_COOKIE } from "./disclaimer";

const prod = process.env.NODE_ENV === "production";

export const LOGIN_TICKET_COOKIE = prod ? "__Secure-wa-login-ticket" : "wa-login-ticket";
export const TRUSTED_DEVICE_COOKIE = prod ? "__Secure-wa-trusted-device" : "wa-trusted-device";

const TICKET_MAX_AGE = 5 * 60; // 5 min — mag niet langer leven dan het login-ticket zelf (API-TTL)
const TRUSTED_MAX_AGE = 30 * 24 * 60 * 60; // 30 dagen

const base = { httpOnly: true, sameSite: "lax" as const, secure: prod, path: "/" };

export async function setLoginTicketCookie(token: string): Promise<void> {
  (await cookies()).set(LOGIN_TICKET_COOKIE, token, { ...base, maxAge: TICKET_MAX_AGE });
}

export async function getLoginTicketCookie(): Promise<string | undefined> {
  return (await cookies()).get(LOGIN_TICKET_COOKIE)?.value;
}

export async function clearLoginTicketCookie(): Promise<void> {
  (await cookies()).set(LOGIN_TICKET_COOKIE, "", { ...base, maxAge: 0 });
}

export async function setTrustedDeviceCookie(token: string): Promise<void> {
  (await cookies()).set(TRUSTED_DEVICE_COOKIE, token, { ...base, maxAge: TRUSTED_MAX_AGE });
}

export async function getTrustedDeviceCookie(): Promise<string | undefined> {
  return (await cookies()).get(TRUSTED_DEVICE_COOKIE)?.value;
}

// Disclaimer-akkoord. Bewust ZONDER maxAge → sessiecookie: hij verdwijnt als de browser sluit,
// zodat de waarschuwing bij elke nieuwe login opnieuw verschijnt. Alleen de aanwezigheid telt.
export async function setDisclaimerCookie(): Promise<void> {
  (await cookies()).set(DISCLAIMER_COOKIE, "1", base);
}

export async function isDisclaimerGeaccepteerd(): Promise<boolean> {
  return (await cookies()).get(DISCLAIMER_COOKIE) !== undefined;
}

export async function clearDisclaimerCookie(): Promise<void> {
  (await cookies()).set(DISCLAIMER_COOKIE, "", { ...base, maxAge: 0 });
}
