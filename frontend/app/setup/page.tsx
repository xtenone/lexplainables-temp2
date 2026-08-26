import { redirect } from "next/navigation";
import { getSetupStatus } from "@/lib/server";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { SetupClient } from "@/components/auth/SetupClient";

export const metadata = { title: "Eerste beheerder · Wetsanalyse" };

export default async function SetupPagina() {
  // Eenmalig: alleen bereikbaar zolang er nog geen enkel account is.
  const { needs_setup } = await getSetupStatus();
  if (!needs_setup) redirect("/login");

  return (
    <AuthFrame
      titel="Eerste beheerder aanmaken"
      onderschrift="Er bestaat nog geen account. Maak hier eenmalig de eerste beheerder aan; daarna voeg je verdere gebruikers toe via het beheerscherm."
    >
      <SetupClient />
    </AuthFrame>
  );
}
