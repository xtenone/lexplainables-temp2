import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { getLoginTicketCookie } from "@/lib/authCookies";
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
    <div className="animate-rise mx-auto max-w-sm space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Tweestapsverificatie</h1>
        <p className="mt-1 text-sm text-muted">
          Voer de 6-cijferige code uit je authenticator-app in.
        </p>
      </div>
      <TwoFactorClient />
    </div>
  );
}
