import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { getSetupStatus } from "@/lib/server";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { LoginClient } from "@/components/auth/LoginClient";

export const metadata = { title: "Inloggen · Wetsanalyse" };

export default async function LoginPagina() {
  // Al ingelogd? Door naar de app. Nog geen account? Eerst de eenmalige registratie.
  const session = await auth();
  if (session?.user) redirect("/");
  const { needs_setup } = await getSetupStatus();
  if (needs_setup) redirect("/setup");

  return (
    <AuthFrame titel="Inloggen" onderschrift="Meld je aan om met Lex, de assistent voor wetsanalyse, te werken.">
      <LoginClient />
    </AuthFrame>
  );
}
