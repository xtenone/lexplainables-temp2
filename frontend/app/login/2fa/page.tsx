import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { getLoginTicketCookie } from "@/lib/authCookies";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { TwoFactorClient } from "@/components/auth/TwoFactorClient";

export const metadata = { title: "Tweestapsverificatie · Wetsanalyse" };

export default async function TweeFactorPagina() {
  // Al ingelogd? Door naar de app.
  const session = await auth();
  if (session?.user) redirect("/");
  // Geen login-ticket (rechtstreeks hierheen genavigeerd of verlopen) → terug naar stap 1.
  const ticket = await getLoginTicketCookie();
  if (!ticket) redirect("/login");

  return (
    <AuthFrame
      titel="Tweestapsverificatie"
      onderschrift="Voer de 6-cijferige code uit je authenticator-app in."
    >
      <TwoFactorClient />
    </AuthFrame>
  );
}
