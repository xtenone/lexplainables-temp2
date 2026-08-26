import { AccountClient } from "@/components/account/AccountClient";
import { PasswordPanel } from "@/components/account/PasswordPanel";

export const metadata = { title: "Account · Wetsanalyse" };

export default function AccountPagina() {
  return (
    <div className="animate-rise mx-auto max-w-2xl space-y-8">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Account</h1>
        <p className="mt-1 text-sm text-muted">
          Wijzig je wachtwoord en beheer je eigen tweestapsverificatie (2FA). 2FA is optioneel; staat
          deze aan, dan vraagt het inloggen om een code uit je authenticator-app.
        </p>
      </div>
      <PasswordPanel />
      <AccountClient />
    </div>
  );
}
