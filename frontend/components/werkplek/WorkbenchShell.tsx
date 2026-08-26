"use client";

import Link from "next/link";
import { useState } from "react";

import { AppSidebar } from "@/components/werkplek/AppSidebar";
import { MobieleTopbar } from "@/components/werkplek/MobieleTopbar";
import { WerkplekClient } from "@/components/werkplek/WerkplekClient";
import type { GesprekSamenvatting } from "@/lib/types";

/** De volledige werkplek-app: links de sidebar (logo → chatgeschiedenis → instellingen/gebruiker),
 *  rechts het chatvenster. `activeId` stuurt de highlight; `mountKey` bepaalt wanneer het chatvenster
 *  vers remount (nieuw/openen) — een gesprek dat tijdens een lopende beurt een id krijgt, remount NIET
 *  (anders breekt de SSE-stream). Op mobiel wordt de sidebar een off-canvas drawer. */
export function WorkbenchShell({
  beginGesprekId = null,
  beginArtefact,
}: {
  /** Gesprek dat bij binnenkomst open moet staan (deep-link vanuit het annotatie-overzicht). */
  beginGesprekId?: string | null;
  /** Annotatie die bij binnenkomst als artefact open moet staan. */
  beginArtefact?: string;
} = {}) {
  const [gesprekken, setGesprekken] = useState<GesprekSamenvatting[]>([]);
  const [activeId, setActiveId] = useState<string | null>(beginGesprekId);
  const [mountKey, setMountKey] = useState(0);
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Verhoogd zodra de chat een gesprek aanmaakte: de sidebar bezit de lijst en haalt hem dan opnieuw.
  const [verversSignaal, setVerversSignaal] = useState(0);
  // Een mislukte hernoem- of verwijderactie mag de werkplek niet blokkeren, maar hoort ook niet stil
  // te blijven: zonder melding is "de nieuwe naam staat er niet" niet te onderscheiden van "de naam
  // is niet aangeslagen", en blijft een gesprek na een bevestigde verwijdering gewoon staan.
  const [fout, setFout] = useState<string | null>(null);

  function nieuwGesprek() {
    setActiveId(null);
    setMountKey((k) => k + 1);
    setDrawerOpen(false);
  }

  function openGesprek(id: string) {
    setActiveId(id);
    setMountKey((k) => k + 1);
    setDrawerOpen(false);
  }

  // Het chatvenster maakte zojuist (bij de eerste beurt) een gesprek aan → highlight bijwerken zónder
  // remount, en de lijst verversen zodat het bovenaan verschijnt.
  function gesprekAangemaakt(id: string) {
    setActiveId(id);
    setVerversSignaal((n) => n + 1);
  }

  const actieveTitel = gesprekken.find((g) => g.id === activeId)?.titel || "Nieuw gesprek";

  return (
    <div className="flex h-full flex-col">
      {/* Waar zit ik? Deze strook hing eerder aan de globale sitekop, en die verborg zichzelf op de
          werkplek — dus juist waar je de hele dag werkt, zag je hem nooit. Nu staat hij bovenaan de
          schil. De klik opent de voorwaarden als dialog (intercepting route), zodat je je gesprek
          niet verlaat. */}
      <Link
        href="/disclaimer"
        className="focus-ring block shrink-0 bg-waarschuwing/10 py-1 text-center text-[0.7rem] text-ink transition-colors hover:bg-waarschuwing/20"
      >
        <span className="font-semibold">Testomgeving — proof of concept.</span>{" "}
        Analyses kunnen verloren gaan. <span className="underline">Lees de voorwaarden</span>
      </Link>

      {fout && (
        <div role="status" className="shrink-0 border-b border-fout/30 bg-fout/10 px-4 py-2 text-center text-[0.8125rem] text-fout">
          {fout}{" "}
          <button
            type="button"
            onClick={() => setFout(null)}
            className="focus-ring rounded font-medium underline underline-offset-2"
          >
            Sluiten
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1">
      <AppSidebar
        activeId={activeId}
        onNieuw={nieuwGesprek}
        onOpen={openGesprek}
        onVerwijderd={(id) => {
          if (id === activeId) nieuwGesprek();
        }}
        onFout={setFout}
        onLijst={setGesprekken}
        verversSignaal={verversSignaal}
        drawerOpen={drawerOpen}
        onDrawerSluit={() => setDrawerOpen(false)}
      />

      {/* Rechterkolom: mobiele topbar + chatvenster */}
      <div className="flex min-w-0 flex-1 flex-col">
        <MobieleTopbar
          titel={actieveTitel}
          onOpenSidebar={() => setDrawerOpen(true)}
          actie={
            <button
              type="button"
              onClick={nieuwGesprek}
              aria-label="Nieuw gesprek"
              className="focus-ring inline-flex items-center justify-center rounded-lg border border-line p-2 text-lint transition-colors hover:bg-surface"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                <path d="M12 5v14M5 12h14" />
              </svg>
            </button>
          }
        />

        <WerkplekClient
          key={mountKey}
          initialGesprekId={activeId}
          beginArtefact={beginArtefact}
          onGesprekAangemaakt={gesprekAangemaakt}
          onGewijzigd={() => setVerversSignaal((n) => n + 1)}
        />
      </div>
      </div>
    </div>
  );
}
