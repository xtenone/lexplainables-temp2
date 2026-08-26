import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { BeheerClient } from "@/components/admin/BeheerClient";

export const metadata = { title: "Beheer · Wetsanalyse" };

export default async function BeheerPagina() {
  // Tweede slot náást de middleware-rolgate: alleen beheerders.
  const session = await auth();
  if (session?.user?.role !== "beheerder") redirect("/");

  return (
    <div className="animate-rise mx-auto max-w-4xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Beheer</h1>
        <p className="mt-1 text-sm text-muted">
          Beheer de LLM-modelprofielen die de analyses aansturen, de wet-catalogus en de gebruikers,
          en bekijk het token-verbruik. Een analyse kiest een profiel op naam; de API-key wordt
          versleuteld bewaard en nooit getoond.
        </p>
      </div>
      <BeheerClient />
    </div>
  );
}
