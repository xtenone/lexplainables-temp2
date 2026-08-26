"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { JAS_KLASSEN, jasStyle } from "@/lib/jas";
import { plaatsPopover } from "@/lib/popover";

/** Waar de popover moet verschijnen: het scherm-rechthoekje van de selectie.
 *
 *  `y` is de ONDERkant en `yBoven` de bovenkant; die tweede is nodig om naar boven te kunnen
 *  uitklappen zonder de selectie zelf af te dekken. */
export interface SelectieDoel {
  fragment: string;
  x: number;
  y: number;
  yBoven: number;
}

/** Keuzemenu bij een tekstselectie: kies een JAS-klasse en de markering is er.
 *
 *  Bewust géén hergebruik van `components/ui/Popover`: die ankert aan een wrapper-element, terwijl
 *  dit aan een muispositie hangt. Escape/klik-buiten volgen wel hetzelfde patroon.
 *
 *  De markering krijgt meteen `human_approved` — je eigen keuze hoef je niet nog eens goed te
 *  keuren — dus hier staat de klasse vast. Vandaar de volle lijst zonder voorsortering: een
 *  "meest waarschijnlijke" bovenaan zou een suggestie zijn die op dit moment niet hoort.
 *
 *  Raakt de selectie de markering die je net had aangeklikt, dan staat bovenaan het aanpassen van
 *  díe markering: inkorten of uitbreiden is de meest voorkomende correctie en hoort één klik te
 *  kosten. Bewust wél een klik en niet automatisch — een selectie die je maakte om te lezen mag
 *  nooit stilzwijgend een annotatie wijzigen, zeker niet zonder undo. */
export function SelectiePopover({
  doel,
  aanpasbaar,
  onKies,
  onPasAan,
  onVraagLex,
  onSluit,
}: {
  doel: SelectieDoel;
  /** De markering die de selectie raakt (klasse + huidig fragment), of niets. */
  aanpasbaar?: { klasse: string; tekst: string };
  onKies: (klasse: string, toelichting: string) => void | Promise<void>;
  onPasAan?: () => void | Promise<void>;
  onVraagLex?: (fragment: string) => void;
  onSluit: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [toelichting, setToelichting] = useState("");
  const [bezig, setBezig] = useState(false);

  useEffect(() => {
    const opKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onSluit();
    };
    const opKlik = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onSluit();
    };
    window.addEventListener("keydown", opKey);
    // Pas ná de huidige klik luisteren, anders sluit de popover meteen weer op de mouseup die hem
    // opende.
    const id = window.setTimeout(() => window.addEventListener("mousedown", opKlik), 0);
    return () => {
      window.removeEventListener("keydown", opKey);
      window.removeEventListener("mousedown", opKlik);
      window.clearTimeout(id);
    };
  }, [onSluit]);

  async function kies(klasse: string) {
    setBezig(true);
    try {
      await onKies(klasse, toelichting.trim());
    } finally {
      setBezig(false);
    }
  }

  // Binnen beeld houden — horizontaal én verticaal. De hoogte meten we ná de eerste render: hij
  // hangt af van het aantal klassen, van de aanpasbaar-strook en van de tekstgrootte van de
  // gebruiker, dus een vaste aanname klopt precies wanneer het misgaat. `useLayoutEffect` doet dat
  // vóór de paint, zodat je hem niet ziet verspringen.
  // 320px, behalve op een scherm dat dat niet heeft: dan de volle breedte min de marges. Zonder die
  // klem stak de popover op een smalle telefoon (≤ 336px, iPhone SE) rechts buiten beeld — de
  // horizontale plaatsing kan een te breed paneel immers nergens meer kwijt.
  const schermbreedte = globalThis.innerWidth || 1024;
  const BREEDTE = Math.min(320, schermbreedte - 16);
  const [hoogte, setHoogte] = useState(280);
  useLayoutEffect(() => {
    const gemeten = ref.current?.offsetHeight;
    if (gemeten && gemeten !== hoogte) setHoogte(gemeten);
  }, [hoogte, doel, aanpasbaar]);

  const plek = plaatsPopover(
    { midden: doel.x, boven: doel.yBoven, onder: doel.y },
    { breedte: BREEDTE, hoogte },
    { breedte: schermbreedte, hoogte: globalThis.innerHeight || 768 },
  );

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Markering toevoegen"
      style={{ position: "fixed", top: plek.top, left: plek.left, width: BREEDTE }}
      className="z-50 max-h-[calc(100dvh-1rem)] overflow-y-auto rounded-kaart border border-line bg-paper p-3 shadow-kaart"
    >
      <p className="mb-2 line-clamp-2 text-xs text-muted">
        <span className="font-medium text-ink">Markeren:</span> “{doel.fragment}”
      </p>

      {aanpasbaar && onPasAan && (
        <div className="mb-2 border-b border-line pb-2">
          <button
            type="button"
            disabled={bezig}
            onClick={async () => {
              setBezig(true);
              try {
                await onPasAan();
              } finally {
                setBezig(false);
              }
            }}
            className="w-full rounded-kaart border border-lint bg-lint/5 px-2 py-1.5 text-left text-xs transition hover:bg-lint/10 disabled:opacity-50"
          >
            <span className="font-medium text-lint">Fragment aanpassen</span>
            <span className="mt-0.5 block text-[0.7rem] text-muted">
              <span className={`rounded px-1 ${jasStyle(aanpasbaar.klasse)}`}>{aanpasbaar.klasse}</span>{" "}
              <span className="line-through">{aanpasbaar.tekst}</span> → “{doel.fragment}”
            </span>
          </button>
          <p className="mt-1.5 text-[0.7rem] text-muted">of markeer als nieuw:</p>
        </div>
      )}

      <div className="mb-2 flex flex-wrap gap-1">
        {JAS_KLASSEN.map((k) => (
          <button
            key={k}
            type="button"
            disabled={bezig}
            onClick={() => void kies(k)}
            className={`min-h-[28px] rounded-full border px-2 py-0.5 text-xs transition-opacity coarse:min-h-[36px] disabled:opacity-50 ${jasStyle(k)}`}
          >
            {k}
          </button>
        ))}
      </div>

      <input
        value={toelichting}
        onChange={(e) => setToelichting(e.target.value)}
        placeholder="Toelichting (optioneel)"
        disabled={bezig}
        className="mb-2 w-full rounded-kaart border border-line bg-paper px-2 py-1.5 text-xs text-ink placeholder-muted focus:border-lint focus:outline-none"
      />

      <div className="flex items-center justify-between">
        {onVraagLex ? (
          <Button size="sm" variant="ghost" disabled={bezig} onClick={() => onVraagLex(doel.fragment)}>
            Vraag Lex
          </Button>
        ) : (
          <span />
        )}
        <Button size="sm" variant="ghost" onClick={onSluit} disabled={bezig}>
          Annuleren
        </Button>
      </div>
    </div>
  );
}
