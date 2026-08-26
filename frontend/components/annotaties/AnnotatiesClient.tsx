"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AnnotatieKaart } from "@/components/annotaties/AnnotatieKaart";
import { AppSidebar } from "@/components/werkplek/AppSidebar";
import { MobieleTopbar } from "@/components/werkplek/MobieleTopbar";
import { Melding } from "@/components/ui/Melding";
import { Skeleton } from "@/components/ui/Skeleton";
import { isApiError, lijstDocumenten, verwijderDocument } from "@/lib/api";
import {
  WEERGAVEN, groepeerPerRegeling, isTeDoen, sorteerTeDoen, weergaveUitParam, zoek,
  type Weergave,
} from "@/lib/annotatieOverzicht";
import type { DocumentSamenvatting } from "@/lib/types";

/** Het annotatie-overzicht: de annotaties los van de gesprekken waarin ze zijn gemaakt.
 *
 *  Twee weergaven op één lijst. *Te doen* is werkvoorraad — wat vraagt nog aandacht, rood eerst.
 *  *Alles* is het archief, gegroepeerd per regeling, want juristen zoeken in wetten en niet in
 *  documenten-op-datum. De stand staat in de URL zodat terugbladeren en delen werken. */
export function AnnotatiesClient({ beginWeergave }: { beginWeergave: Weergave }) {
  const router = useRouter();
  const [docs, setDocs] = useState<DocumentSamenvatting[] | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [weergave, setWeergave] = useState<Weergave>(beginWeergave);
  const [term, setTerm] = useState("");
  // Onder `lg` is de sidebar een drawer. Zonder deze state was er op een smal scherm géén sidebar
  // én geen manier om er een te openen: geen gesprekken, geen account, geen uitloggen.
  const [drawerOpen, setDrawerOpen] = useState(false);

  const laad = useCallback(async () => {
    setFout(null);
    try {
      setDocs(await lijstDocumenten());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setDocs([]);
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    laad();
  }, [laad]);

  function kiesWeergave(nieuw: Weergave) {
    setWeergave(nieuw);
    // `replace`, niet `push`: een wissel tussen twee weergaven van dezelfde lijst is geen stap in de
    // geschiedenis — anders moet je vijf keer terug om weg te komen.
    router.replace(nieuw === "alles" ? "/annotaties?weergave=alles" : "/annotaties", {
      scroll: false,
    });
  }

  async function verwijder(slug: string) {
    try {
      await verwijderDocument(slug);
      setDocs((lijst) => (lijst ?? []).filter((d) => d.slug !== slug));
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : "De annotatie is niet verwijderd.");
    }
  }

  const alles = docs ?? [];
  const gezocht = zoek(alles, term);
  const teDoen = sorteerTeDoen(gezocht.filter(isTeDoen));
  const getoond = weergave === "te-doen" ? teDoen : gezocht;
  const aantalTeDoen = alles.filter(isTeDoen).length;

  return (
    <div className="flex h-screen h-[100dvh] flex-col overflow-hidden bg-surface">
      <div className="flex min-h-0 flex-1">
        <AppSidebar
          activeId={null}
          onNieuw={() => router.push("/workbench")}
          onOpen={(id) => router.push(`/workbench?gesprek=${encodeURIComponent(id)}`)}
          onFout={setFout}
          drawerOpen={drawerOpen}
          onDrawerSluit={() => setDrawerOpen(false)}
        />

        <div className="flex min-w-0 flex-1 flex-col">
        <MobieleTopbar titel="Annotaties" onOpenSidebar={() => setDrawerOpen(true)} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-5xl px-5 py-6 pb-[max(1.5rem,env(safe-area-inset-bottom))]">
            <header className="mb-5">
              <h1 className="font-display text-lg font-semibold text-lint">Annotaties</h1>
              <p className="mt-1 text-sm text-muted">
                Je JAS-annotaties, los van het gesprek waarin ze zijn gemaakt.
              </p>
            </header>

            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              {/* Twee knoppen in plaats van een dropdown: bij twee standen is kiezen sneller dan
                  uitklappen — zelfde afweging als de filters in de reviewlijst. */}
              <div role="group" aria-label="Weergave" className="flex gap-1.5">
                {WEERGAVEN.map((w) => (
                  <button
                    key={w.waarde}
                    type="button"
                    aria-pressed={weergave === w.waarde}
                    onClick={() => kiesWeergave(w.waarde)}
                    className={`focus-ring min-h-[24px] rounded-full border px-2.5 py-0.5 text-[0.7rem] transition coarse:min-h-[44px] ${
                      weergave === w.waarde
                        ? "border-lint bg-lint text-paper"
                        : "border-line text-muted hover:border-lint hover:text-ink"
                    }`}
                  >
                    {w.label}
                    {w.waarde === "te-doen" ? ` (${aantalTeDoen})` : ` (${alles.length})`}
                  </button>
                ))}
              </div>

              <input
                type="search"
                value={term}
                onChange={(e) => setTerm(e.target.value)}
                aria-label="Zoeken in annotaties"
                placeholder="Zoek op wet, artikel of onderwerp"
                className="w-full rounded-field border border-line bg-paper px-3 py-2 text-sm text-ink outline-none transition-colors placeholder:text-faint focus:border-lint focus:ring-2 focus:ring-lint/20 coarse:min-h-[48px] sm:w-72"
              />
            </div>

            {fout && (
              <Melding type="fout" className="mb-4">
                {fout}
              </Melding>
            )}

            {docs === null ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="space-y-3 rounded-button border border-line bg-paper p-4">
                    <Skeleton className="h-4 w-48" />
                    <Skeleton className="h-1.5 w-full" />
                    <Skeleton className="h-3 w-64" />
                  </div>
                ))}
              </div>
            ) : alles.length === 0 ? (
              <p className="text-sm text-muted">
                Nog geen annotaties. Vraag Lex in de werkplek om een artikel te annoteren.
              </p>
            ) : getoond.length === 0 ? (
              <p className="rounded-kaart border border-dashed border-line px-3 py-6 text-center text-sm text-muted">
                {weergave === "te-doen"
                  ? "Niets meer te beoordelen — alles is afgehandeld."
                  : "Geen annotatie die hierop past."}
              </p>
            ) : weergave === "te-doen" ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {getoond.map((d) => (
                  <AnnotatieKaart key={d.slug} doc={d} onVerwijder={verwijder} />
                ))}
              </div>
            ) : (
              <div className="space-y-6">
                {groepeerPerRegeling(getoond).map((regeling) => (
                  <section key={regeling.bwbId}>
                    <div className="mb-3 flex items-baseline gap-3 border-b border-line pb-2">
                      <h2 className="font-display text-base font-semibold text-lint">
                        {regeling.naam}
                      </h2>
                      <span className="font-mono text-xs text-faint">
                        {regeling.documenten.length}
                      </span>
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      {regeling.documenten.map((d) => (
                        <AnnotatieKaart key={d.slug} doc={d} onVerwijder={verwijder} />
                      ))}
                    </div>
                  </section>
                ))}
              </div>
            )}
          </div>
        </main>
        </div>
      </div>
    </div>
  );
}
