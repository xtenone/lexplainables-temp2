import { redirect } from "next/navigation";
import { getSetupStatus } from "@/lib/server";
import { SetupClient } from "@/components/auth/SetupClient";

export const metadata = { title: "Eerste beheerder · Wetsanalyse" };

export default async function SetupPagina() {
  // Eenmalig: alleen bereikbaar zolang er nog geen enkel account is.
  const { needs_setup } = await getSetupStatus();
  if (!needs_setup) redirect("/login");

  return (
    <div className="animate-rise mx-auto max-w-sm space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Eerste beheerder aanmaken</h1>
        <p className="mt-1 text-sm text-muted">
          Er bestaat nog geen account. Maak hier eenmalig de eerste beheerder aan; daarna voeg je
          verdere gebruikers toe via het beheerscherm.
        </p>
      </div>
      <SetupClient />
    </div>
  );
}
