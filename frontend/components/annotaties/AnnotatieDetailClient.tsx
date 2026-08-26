"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppSidebar } from "@/components/werkplek/AppSidebar";
import { MobieleTopbar } from "@/components/werkplek/MobieleTopbar";
import { ArtefactInhoud } from "@/components/werkplek/ArtefactInhoud";
import { ChevronOmlaag } from "@/components/ui/Icoon";
import { Melding } from "@/components/ui/Melding";
import { Skeleton } from "@/components/ui/Skeleton";
import {
  beslis, haalArtikelGraaf, haalDocument, isApiError, verwijderElement, voegElementToe,
  zetDocumentStatus,
} from "@/lib/api";
import { annotatieTitel, isVerwijderd } from "@/lib/annotatie";
import type {
  AnnotatieDocument, BeslissingInvoer, GraafArtikel,
} from "@/lib/types";

/** Eén annotatie op eigen benen: dezelfde inhoud als het artefact in de werkplek, maar met een eigen
 *  URL en zonder chat ernaast.
 *
 *  Daarom ontbreken hier twee dingen bewust. `onVraag` (vraag Lex over dit element) heeft geen
 *  chatveld om iets in klaar te zetten — daarvoor is de knop naar de werkplek. En `ontbrekend` hoort
 *  bij een chatbeurt, niet bij het document, dus die lijst bestaat hier niet. */
export function AnnotatieDetailClient({ slug }: { slug: string }) {
  const router = useRouter();
  const [doc, setDoc] = useState<AnnotatieDocument | null>(null);
  const [info, setInfo] = useState<GraafArtikel | null>(null);
  const [actiefId, setActiefId] = useState<string | undefined>();
  // Twee soorten "niet geladen": een storing (retry heeft zin) en een verwijderd document (retry kan
  // per definitie niet slagen). Die tweede is een toestand, geen fout.
  const [fout, setFout] = useState<string | null>(null);
  const [weg, setWeg] = useState(false);
  const [melding, setMelding] = useState("");
  // Onder `lg` is de sidebar een drawer; zonder deze state stond je hier zonder navigatie.
  const [drawerOpen, setDrawerOpen] = useState(false);

  const laad = useCallback(async () => {
    setFout(null);
    setWeg(false);
    try {
      const document = await haalDocument(slug);
      setDoc(document);
      setInfo(await haalArtikelGraaf(document.bwbId, document.artikel, document.lid));
    } catch (e) {
      if (isVerwijderd(e)) setWeg(true);
      else setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }, [slug]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    laad();
  }, [laad]);

  // De drie mutaties gooien hun fout dóór: `ArtefactInhoud` toont hem bij de kaart waar hij hoort,
  // net als in de werkplek.
  async function beslissing(elementId: string, req: BeslissingInvoer) {
    setDoc(await beslis(slug, elementId, req));
  }

  async function eigenMarkering(invoer: {
    klasse: string; tekst: string; lid: string; toelichting: string; anker: NonNullable<AnnotatieDocument["elementen"][number]["anker"]>;
  }) {
    const oud = new Set((doc?.elementen ?? []).map((e) => e.id));
    const bij = await voegElementToe(slug, invoer);
    setDoc(bij);
    setMelding(`Gemarkeerd als ${invoer.klasse}.`);
    const nieuw = bij.elementen.find((e) => !oud.has(e.id));
    if (nieuw) setActiefId(nieuw.id);
  }

  async function wisEigenMarkering(elementId: string) {
    // De DELETE geeft niets terug, dus hier lokaal filteren — anders dan bij de andere twee, die het
    // hele document terugleveren.
    await verwijderElement(slug, elementId);
    setDoc((d) => (d ? { ...d, elementen: d.elementen.filter((e) => e.id !== elementId) } : d));
    setActiefId((huidig) => (huidig === elementId ? undefined : huidig));
    setMelding("Markering gewist.");
  }

  async function status(nieuweStatus: "geaccordeerd" | "in_review") {
    setDoc(await zetDocumentStatus(slug, nieuweStatus));
    setMelding(nieuweStatus === "geaccordeerd" ? "Annotatie afgerond." : "Annotatie heropend.");
  }

  const titel = doc ? annotatieTitel(doc) : "Annotatie";

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

        <main className="flex min-w-0 flex-1 flex-col bg-paper">
          <MobieleTopbar titel={titel} onOpenSidebar={() => setDrawerOpen(true)} />
          {/* Zelfde afweging als de kop van het artefact hieronder: wrappen in plaats van de titel
              laten wegdrukken door een knop die niet mag krimpen. */}
          <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-line px-5 py-3 lg:pt-[max(0.75rem,env(safe-area-inset-top))]">
            <div className="min-w-0 flex-1 basis-56">
              <Link
                href="/annotaties"
                className="focus-ring inline-flex items-center gap-1 rounded text-xs text-muted transition-colors hover:text-ink"
              >
                <ChevronOmlaag className="rotate-90" /> Alle annotaties
              </Link>
              <p className="truncate text-sm font-medium text-lint">{titel}</p>
            </div>
            {doc && (
              <Link
                href={`/workbench?annotatie=${encodeURIComponent(slug)}`}
                className="focus-ring ml-auto inline-flex min-h-[24px] shrink-0 items-center rounded-full border border-line px-2.5 py-0.5 text-[11px] font-medium text-lint transition-colors hover:bg-surface coarse:min-h-[44px]"
              >
                Openen in de werkplek
              </Link>
            )}
          </div>

          {/* Aankondigingen voor een schermlezer; zonder deze regio verloopt reviewen volledig stil. */}
          <p className="sr-only" aria-live="polite">
            {melding}
          </p>

          {weg && !doc ? (
            <div className="p-5">
              <Melding type="uitleg" titel="Deze annotatie is verwijderd">
                Er valt hier niets meer te openen. Gesprekken waarin hij voorkwam blijven staan.{" "}
                <Link href="/annotaties" className="focus-ring rounded font-medium underline underline-offset-2">
                  Alle annotaties
                </Link>
              </Melding>
            </div>
          ) : fout && !doc ? (
            <div className="p-5">
              <Melding type="fout" titel="Niet geladen">
                {fout}{" "}
                <button type="button" onClick={() => void laad()} className="underline">
                  Opnieuw proberen
                </button>
              </Melding>
            </div>
          ) : !doc || !info ? (
            <div className="space-y-3 p-5">
              <Skeleton className="h-4 w-64" />
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-4 w-40" />
            </div>
          ) : (
            <ArtefactInhoud
              doc={doc}
              info={info}
              actiefId={actiefId}
              onKies={(id) => setActiefId((huidig) => (id && id === huidig ? undefined : id))}
              onBeslissing={beslissing}
              onEigenMarkering={eigenMarkering}
              onWisEigenMarkering={wisEigenMarkering}
              onStatus={status}
            />
          )}
        </main>
      </div>
    </div>
  );
}
