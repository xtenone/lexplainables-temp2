import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { InstellingenInhoud } from "@/components/instellingen/InstellingenInhoud";
import { isAdminTab, tabUitPad } from "@/lib/instellingen";

export const metadata = { title: "Instellingen · Wetsanalyse" };

/** De volledige instellingenpagina: wat je krijgt bij een directe link, een refresh of navigatie
 *  van buiten de werkplek. Vanuit de app onderschept `app/@modal/(.)instellingen/…` dit pad en toont
 *  dezelfde inhoud als dialog over de werkplek heen.
 *
 *  Er is geen globale chrome meer; deze pagina draagt daarom zelf haar volle hoogte én de kop met
 *  de weg terug naar de werkplek. */
export default async function InstellingenPagina({
  params,
}: {
  params: Promise<{ tab?: string[] }>;
}) {
  const { tab } = await params;
  const actief = tabUitPad(tab);
  const session = await auth();
  const isBeheerder = session?.user?.role === "beheerder";

  // Tweede slot náást de rolgate in auth.config.ts, net als het oude app/beheer/page.tsx.
  if (isAdminTab(actief) && !isBeheerder) redirect("/");

  return (
    <div className="flex h-screen h-[100dvh] flex-col overflow-hidden bg-surface">
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line bg-paper px-5 py-3.5 pt-[max(0.875rem,env(safe-area-inset-top))]">
        <h1 className="font-display text-base font-semibold text-lint">Instellingen</h1>
        <Link
          href="/workbench"
          className="rounded-kaart px-2.5 py-1.5 text-sm text-muted transition-colors hover:bg-surface hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          Terug naar de werkplek
        </Link>
      </div>
      <div className="mx-auto flex min-h-0 w-full max-w-5xl flex-1 flex-col overflow-hidden bg-paper">
        <InstellingenInhoud actief={actief} isBeheerder={isBeheerder} />
      </div>
    </div>
  );
}
