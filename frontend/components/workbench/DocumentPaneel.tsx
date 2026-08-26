"use client";

import { useEffect, useMemo, useRef } from "react";

import { jasStyle } from "@/lib/jas";
import { lidUitOffset, offsetUit, snapSelectie, vindPositie, type LidRegel } from "@/lib/selectie";
import { bronVan } from "@/lib/annotatie";
import type { Anker } from "@/lib/types";

/** Minimaal element voor highlighting: klasse + letterlijk fragment (+ optioneel id/anker/herkomst). */
export interface Markeerbaar {
  id?: string;
  klasse: string;
  tekst: string;
  herkomst?: string;
  anker?: Anker | null;
}

interface Segment {
  tekst: string;
  klasse?: string;
  id?: string;
  herkomst?: string;
}

/** Knip `bron` in segmenten, met hoogstens ÉÉN gemarkeerd: de geselecteerde.
 *
 *  Alles tegelijk kleuren was onleesbaar én onvolledig. Twee markeringen kunnen niet op dezelfde
 *  tekst liggen, dus een markering die binnen een langere valt — een Rechtsobject in een zin die als
 *  geheel een Afleidingsregel is — verdween gewoon uit beeld. Nu is de reviewlijst de ingang en laat
 *  de tekst zien wáár het gekozen element staat; zonder selectie blijft de tekst schoon.
 *
 *  De positie komt uit `vindPositie`: eerst het anker (exacte offsets), dan de omringende tekst, dan
 *  het eerste voorkomen. Dat houdt twee identieke fragmenten in één artikel uit elkaar — zonder
 *  anker zou de tweede "De ontvanger" op de eerste landen.
 */
export function segmenteer(bron: string, elementen: Markeerbaar[], actiefId?: string): Segment[] {
  const el = actiefId ? elementen.find((e) => e.id === actiefId) : undefined;
  const fragment = el?.tekst.trim() ?? "";
  const start = fragment ? vindPositie(bron, fragment, el?.anker, []) : -1;
  if (!el || start < 0) return [{ tekst: bron }];

  const eind = start + fragment.length;
  return [
    ...(start > 0 ? [{ tekst: bron.slice(0, start) }] : []),
    { tekst: bron.slice(start, eind), klasse: el.klasse, id: el.id, herkomst: el.herkomst },
    ...(eind < bron.length ? [{ tekst: bron.slice(eind) }] : []),
  ];
}

export function DocumentPaneel({
  opschrift,
  regels,
  elementen,
  actiefId,
  onKies,
  onSelectie,
}: {
  opschrift: string;
  /** De artikeltekst als regels mét hun lidnummer (`regelsVan`). Niet als kale strings: het lidnummer
   *  is niet uit de volgorde af te leiden, en een markering draagt het wél. */
  regels: LidRegel[];
  elementen: Markeerbaar[];
  actiefId?: string;
  onKies?: (id?: string) => void;
  /** De jurist heeft tekst geselecteerd om zelf te markeren. Weglaten = alleen-lezen. */
  onSelectie?: (sel: {
    fragment: string; start: number; eind: number; lid: string; bron: string;
    x: number; y: number; yBoven: number;
  }) => void;
}) {
  const bron = useMemo(() => bronVan(regels), [regels]);
  const segmenten = useMemo(() => segmenteer(bron, elementen, actiefId), [bron, elementen, actiefId]);
  const gekozen = actiefId ? elementen.find((e) => e.id === actiefId) : undefined;
  const tekstRef = useRef<HTMLParagraphElement>(null);
  const markRef = useRef<HTMLElement>(null);

  // Een selectie eindigt niet altijd met een muisklik. Met Shift+pijltjes komt er geen enkel
  // muisevent langs — dan is zelf markeren met het toetsenbord onmogelijk (WCAG 2.1.1) — en op een
  // aanraakscherm laat het verslepen van een selectiegreep geen `mouseup` achter. Beide luisteraars
  // hangen aan het document omdat de vinger of de cursor buiten de alinea kan loslaten;
  // `verwerkSelectie` controleert zelf al of de selectie wél binnen de tekst valt.
  useEffect(() => {
    if (!onSelectie) return;
    const opToets = (e: KeyboardEvent) => {
      // Alleen na een selectie-gebaar kijken: anders draait dit bij elke toetsaanslag in de pagina.
      if (e.shiftKey || e.key === "Shift") verwerkSelectie();
    };
    document.addEventListener("keyup", opToets);
    document.addEventListener("touchend", verwerkSelectie);
    return () => {
      document.removeEventListener("keyup", opToets);
      document.removeEventListener("touchend", verwerkSelectie);
    };
    // Bewust zonder dependency-array: `verwerkSelectie` leest de actuele bron en moet elke render
    // vers zijn, net als de sneltoetsen in het artefactpaneel.
  });

  // De gekozen markering in beeld brengen. Zonder dit sta je bij een lange bepaling naar de verkeerde
  // alinea te kijken terwijl je in de lijst al drie elementen verder bent.
  useEffect(() => {
    if (!actiefId || !markRef.current) return;
    const rustig = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    markRef.current.scrollIntoView({ block: "center", behavior: rustig ? "auto" : "smooth" });
  }, [actiefId]);

  /** Zet een DOM-selectie om naar offsets in `bron`.
   *
   *  Dit kan omdat de alinea één aaneengesloten reeks span/mark is waarvan de tekstknopen samen
   *  exact `bron` vormen — dus de lengtes optellen tot de startknoop geeft de absolute positie.
   *  De rekenstap zelf staat in `lib/selectie.ts` en is daar getest; hier blijft alleen de
   *  DOM-wandeling over, die in de node-omgeving van vitest toch niet te testen is. */
  function verwerkSelectie() {
    if (!onSelectie) return;
    const sel = window.getSelection();
    const houder = tekstRef.current;
    if (!sel || sel.isCollapsed || sel.rangeCount === 0 || !houder) return;
    const range = sel.getRangeAt(0);
    if (!houder.contains(range.commonAncestorContainer)) return;

    const knopen: Text[] = [];
    const walker = document.createTreeWalker(houder, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) knopen.push(n as Text);

    const lengtes = knopen.map((n) => n.data.length);
    const vanIdx = knopen.indexOf(range.startContainer as Text);
    const totIdx = knopen.indexOf(range.endContainer as Text);
    if (vanIdx < 0 || totIdx < 0) return;

    const ruwStart = offsetUit(lengtes, vanIdx, range.startOffset);
    const ruwEind = offsetUit(lengtes, totIdx, range.endOffset);
    const { start, eind } = snapSelectie(bron, ruwStart, ruwEind);
    if (eind - start < 2) return;   // losse letter of alleen witruimte: geen markering

    const rect = range.getBoundingClientRect();
    onSelectie({
      fragment: bron.slice(start, eind),
      start,
      eind,
      lid: lidUitOffset(regels, start),
      bron,
      x: rect.left + rect.width / 2,
      y: rect.bottom,
      yBoven: rect.top,
    });
  }

  return (
    <div className="rounded-kaart border border-line bg-white p-5 shadow-zacht">
      {opschrift && <h2 className="mb-3 font-display text-lg font-semibold text-lint">{opschrift}</h2>}
      {elementen.length > 0 && (
        <div className="mb-3 flex items-center justify-between gap-3 rounded-kaart bg-lint/5 px-3 py-2 text-xs text-muted">
          {gekozen ? (
            <>
              <span>
                <span className="font-medium text-ink">{gekozen.klasse}</span> in beeld
              </span>
              <button
                type="button"
                onClick={() => onKies?.(undefined)}
                className="shrink-0 font-medium text-lint underline underline-offset-2 hover:no-underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
              >
                Verbergen
              </button>
            </>
          ) : (
            <span>
              Kies een markering in de lijst om te zien waar hij staat, of selecteer tekst om zelf te
              markeren.
            </span>
          )}
        </div>
      )}
      {/* Volle breedte, op verzoek van de jurist (19 aug 2026). Hier stond een leeskolom van ~66
          tekens — de klassieke leesmaat — maar op de losse annotatiepagina begrenst niets anders de
          breedte, en dan plakt een smalle kolom tegen de linkerrand van een breed scherm alsof er
          harde regelafbrekingen in de wettekst zitten. De afweging is bekend en bewust gemaakt:
          lange regels lezen minder prettig, maar er past meer tekst tegelijk in beeld. Verander dit
          dus niet "terug" zonder het te vragen.

          `whitespace-pre-wrap` blijft nodig: de leden worden met `\n\n` aaneengeregen (`bronVan`),
          en de ankers rekenen met exact die brontekst. */}
      <p
        ref={tekstRef}
        onMouseUp={verwerkSelectie}
        className="whitespace-pre-wrap text-[0.95rem] leading-7 text-ink"
      >
        {segmenten.map((s, i) =>
          s.klasse ? (
            // Nadrukkelijk géén `<button>`: die is inline-block en dus één atomaire box. Zodra de
            // markering over meer dan één regel liep, groeide hij naar de volle regelbreedte — een
            // rechthoekig blok tot aan de rechterrand in plaats van een markering om de woorden — en
            // zakte de tekst erna (bij een hele zin: de afsluitende punt) naar de volgende regel.
            // Een `<mark>` is inline en breekt dus gewoon met de tekst mee; `box-decoration-clone`
            // tekent achtergrond, afronding en `px-0.5` opnieuw op elk regelfragment, anders krijgt
            // alleen het eerste stuk een linkerrand en het laatste een rechter. Weghalen = de blokvorm
            // terug. De WCAG-2.1.1-eis die de knop kwam oplossen (focusbaar en met het toetsenbord te
            // bedienen) staat hier als `role="button"` + `tabIndex` + `onKeyDown`.
            <mark
              key={i}
              ref={s.id === actiefId ? markRef : undefined}
              role="button"
              tabIndex={0}
              onClick={() => onKies?.(s.id)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" && e.key !== " ") return;
                e.preventDefault();   // Space scrolt anders de tekst weg onder je vinger vandaan
                onKies?.(s.id);
              }}
              aria-label={`${s.klasse}: ${s.tekst}${s.herkomst === "mens" ? " — door jou gemarkeerd" : ""}`}
              title={s.herkomst === "mens" ? `${s.klasse} — door jou gemarkeerd` : s.klasse}
              className={`focus-ring box-decoration-clone cursor-pointer rounded px-0.5 ${jasStyle(s.klasse)} ${
                s.herkomst === "mens" ? "underline decoration-dotted underline-offset-2" : ""
              } ${actiefId && s.id === actiefId ? "ring-2 ring-lint" : ""}`}
            >
              {s.tekst}
            </mark>
          ) : (
            <span key={i}>{s.tekst}</span>
          ),
        )}
      </p>
    </div>
  );
}
