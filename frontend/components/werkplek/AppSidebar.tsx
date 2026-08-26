"use client";

import { useCallback, useEffect, useState } from "react";

import { Dialog } from "@/components/ui/Dialog";
import { GesprekSidebar } from "@/components/werkplek/GesprekSidebar";
import { hernoemGesprek, lijstGesprekken, verwijderGesprek } from "@/lib/api";
import type { GesprekSamenvatting } from "@/lib/types";

interface Props {
  /** Welk gesprek is actief (highlight). `null` op schermen buiten de chat. */
  activeId: string | null;
  onNieuw: () => void;
  onOpen: (id: string) => void;
  /** Het actieve gesprek is zojuist verwijderd — de aanroeper beslist wat er dan gebeurt. */
  onVerwijderd?: (id: string) => void;
  /** Hapering bij hernoemen/verwijderen. Wie de sidebar plaatst, bepaalt waar de melding landt. */
  onFout?: (melding: string) => void;
  /** De lijst zoals hij nu is — bv. om er een schermtitel uit af te leiden. */
  onLijst?: (gesprekken: GesprekSamenvatting[]) => void;
  /** Verhoog dit getal om de lijst opnieuw op te halen (bv. nadat een beurt een gesprek aanmaakte). */
  verversSignaal?: number;
  /** Mobiel: staat de off-canvas drawer open, en hoe sluit hij. */
  drawerOpen?: boolean;
  onDrawerSluit?: () => void;
}

/** De gesprekssidebar met alles eromheen: laden, hernoemen, verwijderen, en de mobiele drawer.
 *
 *  Gedeeld door de werkplek en het annotatie-overzicht, zodat je bij het wisselen niet "uit de app"
 *  stapt — dat is wat Claude's artifacts-tab ook doet: de sidebar blijft, alleen het hoofdgebied
 *  verandert. De handlers verschillen wél per scherm: in de werkplek wisselt een klik van gesprek in
 *  lokale state, op het overzicht navigeert hij terug naar de werkplek. */
export function AppSidebar({
  activeId, onNieuw, onOpen, onVerwijderd, onFout, onLijst, verversSignaal = 0,
  drawerOpen = false, onDrawerSluit,
}: Props) {
  const [gesprekken, setGesprekken] = useState<GesprekSamenvatting[]>([]);
  const [laden, setLaden] = useState(true);

  const verversLijst = useCallback(() => {
    lijstGesprekken()
      .then((lijst) => {
        setGesprekken(lijst);
        onLijst?.(lijst);
      })
      .catch(() => {})
      .finally(() => setLaden(false));
    // `onLijst` bewust buiten de deps: het is vaak een inline callback en zou de fetch anders bij
    // elke render opnieuw laten lopen.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    verversLijst();
  }, [verversLijst, verversSignaal]);

  async function hernoem(id: string, titel: string) {
    try {
      await hernoemGesprek(id, titel);
      verversLijst();
    } catch {
      onFout?.("De nieuwe naam is niet opgeslagen.");
    }
  }

  /** De bevestiging zit in de knop zelf (`BevestigKnop`, twee klikken) — hetzelfde gebaar als in het
   *  artefact; geen `window.confirm` midden in een app met een eigen vormtaal. */
  async function verwijder(id: string) {
    try {
      await verwijderGesprek(id);
      // Meteen uit de lijst halen en dáárna pas verversen: de DELETE is al geslaagd, dus wachten op
      // een round trip laat de rij onnodig staan — en het verwijderde gesprek is meestal het gesprek
      // dat je open hebt.
      setGesprekken((lijst) => lijst.filter((g) => g.id !== id));
      onVerwijderd?.(id);
      verversLijst();
    } catch {
      onFout?.("Het gesprek is niet verwijderd.");
    }
  }

  const inhoud = (extra?: { onSluit: () => void }) => (
    <GesprekSidebar
      gesprekken={gesprekken}
      activeId={activeId}
      onNieuw={onNieuw}
      onOpen={onOpen}
      onHernoem={hernoem}
      onVerwijder={verwijder}
      laden={laden}
      onSluit={extra?.onSluit}
    />
  );

  return (
    <>
      <aside className="hidden w-[17rem] shrink-0 border-r border-line lg:block">{inhoud()}</aside>

      {/* Mobiele off-canvas drawer. Via `Dialog` en niet als eigen constructie: die draagt de
          focus-trap, Escape en de backdrop. */}
      {drawerOpen && onDrawerSluit && (
        <Dialog
          label="Gesprekken"
          variant="drawer"
          wrapperClassName="lg:hidden"
          onSluit={onDrawerSluit}
        >
          {inhoud({ onSluit: onDrawerSluit })}
        </Dialog>
      )}
    </>
  );
}
