// Zet (POST) of wist (DELETE) de disclaimer-sessiecookie. Praat niet met de upstream-API — dit is
// puur browserstatus, zie lib/disclaimer.ts voor waarom het geen accountvlag is.
//
// DELETE wordt bij het uitloggen aangeroepen (het gebruikersmenu in de sidebar): een
// sessiecookie overleeft een logout
// binnen dezelfde browsersessie, en dan zou de vólgende gebruiker de disclaimer niet zien.
//
// De Origin-check in auth.config.ts dekt beide methodes; een same-origin fetch komt er langs.
import { clearDisclaimerCookie, setDisclaimerCookie } from "@/lib/authCookies";

export const dynamic = "force-dynamic";

export async function POST() {
  await setDisclaimerCookie();
  return new Response(null, { status: 204 });
}

export async function DELETE() {
  await clearDisclaimerCookie();
  return new Response(null, { status: 204 });
}
