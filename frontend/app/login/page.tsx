import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { getSetupStatus } from "@/lib/server";
import { LoginClient } from "@/components/auth/LoginClient";

export const metadata = { title: "Inloggen · Wetsanalyse" };

export default async function LoginPagina() {
  // Al ingelogd? Door naar de app. Nog geen account? Eerst de eenmalige registratie.
  const session = await auth();
  if (session?.user) redirect("/");
  const { needs_setup } = await getSetupStatus();
  if (needs_setup) redirect("/setup");

  return (
    <div className="animate-rise mx-auto max-w-sm space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Inloggen</h1>
        <p className="mt-1 text-sm text-muted">Meld je aan om de wetsanalyses te bekijken en te bewerken.</p>
      </div>
      <LoginClient />
    </div>
  );
}
