"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { foutTekst } from "@/lib/api";

import { Melding } from "@/components/ui/Melding";
import { DocumentPaneel } from "@/components/workbench/DocumentPaneel";
import { ExportKnop } from "@/components/workbench/ExportKnop";
import { OntbrekendLijst } from "@/components/workbench/OntbrekendLijst";
import { ReviewQueue, type OpenRij } from "@/components/workbench/ReviewQueue";
import { SelectiePopover, type SelectieDoel } from "@/components/workbench/SelectiePopover";
import {
  DOCUMENT_STATUS_LABEL, DOCUMENT_STATUS_STYLE, bronVan, isDocumentVergrendeld, isVergrendeld,
  overlaptSelectie, pastInFilter, regelsVan, sorteerReview, volgendeElement, type ReviewFilter,
} from "@/lib/annotatie";
import { maakAnker, vindPositie } from "@/lib/selectie";
import type {
  AnnotatieDocument, AnnotatieElement, BeslissingInvoer, DocumentStatus, GraafArtikel, OntbrekendItem,
} from "@/lib/types";

export interface ArtefactInhoudProps {
  doc: AnnotatieDocument;
  info: GraafArtikel;
  ontbrekend?: OntbrekendItem[];
  actiefId?: string;
  onKies: (id?: string) => void;
  onBeslissing: (elementId: string, req: BeslissingInvoer) => Promise<void>;
  /** De jurist markeert zelf een fragment. Weglaten maakt het paneel alleen-lezen. */
  onEigenMarkering?: (invoer: {
    klasse: string; tekst: string; lid: string; toelichting: string;
    anker: ReturnType<typeof maakAnker>;
  }) => Promise<void>;
  /** Eigen markering wissen. Een agent-voorstel verwérp je — dat gaat via `onBeslissing`. */
  onWisEigenMarkering?: (elementId: string) => Promise<void>;
  /** Zet een vraag over een element klaar in het centrale chatvenster. Bestaat alleen in de
   *  werkplek; op de eigen pagina van een annotatie is er geen chat om iets in klaar te zetten. */
  onVraag?: (el: AnnotatieElement) => void;
  /** Afronden of heropenen. Weglaten verbergt de knop (bv. in een alleen-lezen weergave). */
  onStatus?: (status: "geaccordeerd" | "in_review") => Promise<void>;
  /** Meegeven in de dialoogschil (het kruisje, en de laatste laag van Escape); weglaten op de
   *  eigen pagina, die niets te sluiten heeft. */
  onSluiten?: () => void;
}

/** De inhoud van het annotatie-artefact: brongetrouwe artikeltekst met letterlijke highlights, en
 *  daaronder de review-queue.
 *
 *  Bewust los van zijn schil, zoals `DisclaimerClient` en `InstellingenInhoud` dat al doen: in de
 *  werkplek zit hij in een `Dialog` (`ArtefactPaneel`), op `/annotaties/<slug>` in een gewone
 *  pagina. Eén inhoud, twee schillen — anders gaan de twee weergaven uit elkaar lopen. */
export function ArtefactInhoud({
  doc, info, ontbrekend, actiefId, onKies, onBeslissing, onEigenMarkering,
  onWisEigenMarkering, onVraag, onStatus, onSluiten,
}: ArtefactInhoudProps) {
  const opschrift = `${info.citeertitel || doc.bwbId} — artikel ${info.artikel}${doc.lid ? ` lid ${doc.lid}` : ""}`;
  // Eén keer per artikel opbouwen, niet per render: de regels zijn de identiteit waarop het
  // documentpaneel zijn eigen `useMemo`'s hangt, dus een verse array per render zette die uit.
  const regels = useMemo(() => regelsVan(info), [info]);
  const bron = useMemo(() => bronVan(regels), [regels]);

  // Eén lus, twee antwoorden — beide uit dezelfde `vindPositie` als de weergave, dus ze kloppen
  // altijd met wat je ziet:
  //  • welke markeringen niet (meer) in de wettekst te vinden zijn (die vielen stilzwijgend weg);
  //  • waar elke markering staat, als sorteersleutel binnen een JAS-klasse.
  const { zwevendeIds, posities } = useMemo(() => {
    const zwevend = new Set<string>();
    const pos = new Map<string, number>();
    for (const el of doc.elementen) {
      if (el.lifecycle === "rejected") continue;
      const idx = vindPositie(bron, el.tekst.trim(), el.anker, []);
      if (idx < 0) zwevend.add(el.id);
      else pos.set(el.id, idx);
    }
    return { zwevendeIds: zwevend, posities: pos };
  }, [doc.elementen, bron]);
  const [selectie, setSelectie] = useState<(SelectieDoel & { start: number; eind: number; lid: string; bron: string }) | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [filter, setFilter] = useState<ReviewFilter>("alles");
  const [open, setOpen] = useState<OpenRij>("geen");
  const [statusBezig, setStatusBezig] = useState(false);

  // Raakt de selectie de markering die in beeld staat? Dan is dit vermoedelijk een correctie op dát
  // element (inkorten/uitbreiden) en niet een nieuwe markering. De positie komt uit dezelfde
  // `vindPositie` als de weergave, dus het antwoord klopt altijd met wat je ziet.
  const actief = doc.elementen.find((e) => e.id === actiefId && e.lifecycle !== "rejected");
  const actiefBereik = (() => {
    if (!actief || !selectie) return null;
    const start = vindPositie(selectie.bron, actief.tekst.trim(), actief.anker, []);
    return start < 0 ? null : { start, eind: start + actief.tekst.trim().length };
  })();
  // Een selectie die exact het huidige fragment is, is geen correctie: dan zou "aanpassen" een lege
  // wijziging wegschrijven en het auditspoor vervuilen met een beslissing zonder inhoud.
  const teCorrigeren =
    actief && actiefBereik && selectie && selectie.fragment !== actief.tekst
    && overlaptSelectie(selectie, actiefBereik)
      ? actief
      : undefined;

  // De getoonde volgorde: sorteren op de VOLLEDIGE lijst, dan pas filteren — zo verandert een
  // filterwissel de onderlinge volgorde niet. Hier berekend en niet in de lijst, zodat het toetsenbord
  // gegarandeerd dezelfde volgorde doorloopt als je ziet en de positiekaart maar op één plek bestaat.
  const getoond = useMemo(
    () => sorteerReview(doc.elementen, posities).filter((el) => pastInFilter(el, filter)),
    [doc.elementen, filter, posities],
  );

  /** De selectie loslaten, inclusief die in de DOM.
   *
   *  Dat laatste is nodig sinds een selectie ook op `touchend`/`keyup` wordt opgepikt: laat je alleen
   *  de state los, dan staat de tekst in de browser nog steeds geselecteerd en klapt de popover bij de
   *  eerstvolgende tik of Shift-toets meteen weer open. */
  const sluitSelectie = useCallback(() => {
    setSelectie(null);
    window.getSelection()?.removeAllRanges();
  }, []);

  /** Escape pelt één laag af in plaats van meteen alles te sluiten: eerst de selectie in de tekst,
   *  dan de open bedieningsrij, dan het gekozen element — en pas als er niets meer openstaat gaat
   *  het paneel dicht (in de dialoogschil; op een eigen pagina is er niets te sluiten en stopt het
   *  afpellen daar).
   *
   *  Dit hing eerder aan `Dialog.onEscape`, maar die schil bestaat nu niet altijd. De afhandeling
   *  hoort bij de inhoud die de lagen kent; de dialoogschil geeft `Dialog` daarom een no-op mee,
   *  anders zou Escape twee dingen tegelijk doen. */
  const opEscape = useCallback(() => {
    if (selectie) sluitSelectie();
    else if (open !== "geen") setOpen("geen");
    else if (actiefId) onKies(undefined);
    else onSluiten?.();
  }, [selectie, open, actiefId, onKies, onSluiten, sluitSelectie]);

  /** Een afgerond document is bevroren. De api weigert elke mutatie met een 409; hier leggen we de
   *  bediening stil zodat de jurist die fout nooit tegenkomt — een knop die alleen nog een
   *  foutmelding oplevert is erger dan geen knop. Heropenen staat in de kop en is één klik. */
  const vergrendeld = isDocumentVergrendeld(doc);

  /** Afronden of heropenen. De fout landt in dezelfde melding als de beslissingen — de jurist hoeft
   *  niet op twee plekken te kijken. */
  async function zetStatus(status: "geaccordeerd" | "in_review") {
    if (!onStatus) return;
    setFout(null);
    setStatusBezig(true);
    try {
      await onStatus(status);
    } catch (e) {
      setFout(foutTekst(e, "De status is niet gewijzigd."));
    } finally {
      setStatusBezig(false);
    }
  }

  /** Sneltoetsen. Bewust inactief zodra de focus in een invoerveld staat: anders keur je iets goed
   *  door "a" te typen in een toelichting. Escape werkt altijd — dat is de uitweg. */
  useEffect(() => {
    function opToets(e: KeyboardEvent) {
      const doel = e.target as HTMLElement | null;
      const inVeld =
        !!doel && (doel.tagName === "INPUT" || doel.tagName === "TEXTAREA" || doel.isContentEditable);
      // Escape eerst: dat is de uitweg, precies zoals `Dialog` hem afhandelde toen die schil er
      // altijd was. Wél in de eigen invoervelden van het artefact (een toelichting annuleren), maar
      // NIET vanuit de chat ernaast: in de kolom-variant staat die naast het artefact, en dan sloot
      // Escape tijdens het typen van een vraag ineens het paneel waar je in werkte.
      if (e.key === "Escape") {
        if (inVeld && !!doel?.closest("[data-artefact]")) opEscape();
        else if (!inVeld) opEscape();
        return;
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (inVeld) return;

      const stap = (richting: 1 | -1) => {
        const volgend = volgendeElement(getoond, actiefId, richting);
        if (volgend) {
          e.preventDefault();
          setOpen("geen");
          onKies(volgend.id);
        }
      };

      if (e.key === "j" || e.key === "ArrowDown") return stap(1);
      if (e.key === "k" || e.key === "ArrowUp") return stap(-1);
      if (!actiefId) return;
      const actiefEl = doc.elementen.find((el) => el.id === actiefId);
      if (!actiefEl) return;

      // Ook het slot op dít element telt: anders opent `x` een redenen-rij die alleen nog een 409
      // kan opleveren. De sneltoets doet precies wat de knop doet — of hij doet niets.
      if (vergrendeld || isVergrendeld(actiefEl)) return;

      if (e.key === "a") {
        e.preventDefault();
        void keurGoed(actiefEl.id);
      } else if (e.key === "x") {
        e.preventDefault();
        setOpen((h) => (h === "verwerp" ? "geen" : "verwerp"));
      } else if (e.key === "c") {
        e.preventDefault();
        setOpen((h) => (h === "klasse" ? "geen" : "klasse"));
      }
    }
    window.addEventListener("keydown", opToets);
    return () => window.removeEventListener("keydown", opToets);
    // Bewust zónder dependency-array: de handler leest de actuele selectie, de getoonde lijst en de
    // open rij, en moet dus elke render vers zijn. Een dependency-lijst zou hier alle state opsommen
    // die de handler aanraakt, met als enige winst dat de listener minder vaak wisselt.
  });

  /** Elke beslissing loopt hierlangs, zodat een mislukking bij de kaart landt en niet in de
   *  chatthread. De aanroeper (`WerkplekClient`) gooit de fout bewust dóór. */
  async function beslis(elementId: string, req: BeslissingInvoer) {
    if (vergrendeld) return;
    setFout(null);
    try {
      await onBeslissing(elementId, req);
    } catch (e) {
      setFout(foutTekst(e, "De wijziging is niet opgeslagen."));
      throw e;
    }
  }

  /** Wissen loopt om dezelfde reden hierlangs: de fout hoort bij de kaart, niet in de chat. */
  async function wis(elementId: string) {
    if (vergrendeld) return;
    setFout(null);
    try {
      await onWisEigenMarkering?.(elementId);
    } catch (e) {
      setFout(foutTekst(e, "De markering is niet gewist."));
      throw e;
    }
  }

  /** Goedkeuren en doorspringen naar het volgende dat nog aandacht vraagt. Dat doorspringen is de
   *  hele winst van een reviewlijst; blijven staan op iets dat af is kost per element een klik. */
  async function keurGoed(elementId: string) {
    if (vergrendeld) return;
    const volgend = volgendeElement(getoond, elementId, 1, true);
    await beslis(elementId, { type: "approve" });
    setOpen("geen");
    onKies(volgend?.id);
  }

  /** Het fragment van de actieve markering vervangen door de selectie. Het anker gaat mee: zonder
   *  dat wijzen de offsets naar het oude fragment en springt de markering na herladen. */
  async function pasFragmentAan() {
    if (vergrendeld || !selectie || !teCorrigeren) return;
    setFout(null);
    try {
      await beslis(teCorrigeren.id, {
        type: "edit",
        review_reason: "tekst",
        wijziging: {
          tekst: selectie.fragment,
          anker: maakAnker(selectie.bron, selectie.start, selectie.eind, selectie.lid),
        },
      });
      sluitSelectie();
    } catch (e) {
      setFout(foutTekst(e, "Aanpassen is niet gelukt."));
    }
  }

  /** Zelf markeren, of een ontbrekend element toevoegen: beide lopen hierlangs zodat een mislukking
   *  in de melding van het paneel landt. De ontbrekend-lijst kreeg eerder `onEigenMarkering`
   *  rechtstreeks doorgegeven en faalde daardoor stil — de klik leek genegeerd te worden. */
  async function markeer(invoer: {
    klasse: string; tekst: string; lid: string; toelichting: string; anker: ReturnType<typeof maakAnker>;
  }): Promise<void> {
    if (vergrendeld || !onEigenMarkering) return;
    setFout(null);
    try {
      // Heeft de bepaling geen genummerde leden, dan valt het lid terug op de afbakening van het
      // document zelf — beter dat dan een leeg veld op een document dat wél over één lid gaat.
      await onEigenMarkering({ ...invoer, lid: invoer.lid || doc.lid || "" });
      sluitSelectie();
    } catch (e) {
      setFout(foutTekst(e, "Markeren is niet gelukt."));
    }
  }

  /** De selectie in de tekst als markering vastleggen. */
  async function markeerSelectie(klasse: string, toelichting: string) {
    if (vergrendeld || !selectie) return;
    await markeer({
      klasse,
      tekst: selectie.fragment,
      lid: selectie.lid,
      toelichting,
      anker: maakAnker(selectie.bron, selectie.start, selectie.eind, selectie.lid),
    });
  }

  return (
    // `data-artefact` bakent af wat "binnen het artefact" is. De keydown-handler hangt aan `window`
    // (het paneel is in de kolom-variant niet modaal), en moet Escape uit de chat ernaast kunnen
    // onderscheiden van Escape in een eigen invoerveld.
    <div data-artefact className="flex min-h-0 flex-1 flex-col">
        {/* Kop in twee vaste regels: titel + sluitknop, daaronder de acties.

            Het kruisje hoort altijd rechtsboven te staan, op dezelfde plek als in het
            instellingenvenster en de gesprekkendrawer — sluiten is de uitweg, en die zoek je op één
            plek. In één wrappende rij verhuisde het mee met de knoppen zodra de ruimte krap werd, en
            dan stond het op een telefoon ineens onder de titel tussen Exporteren en Afronden.

            De acties krijgen hun eigen regel en lijnen rechts uit, onder het kruisje. Dat kost op een
            breed scherm een regel hoogte, en dat is de prijs voor een sluitknop die niet wandelt. */}
        <div className="flex shrink-0 flex-col gap-2 border-b border-line px-5 py-3.5 pt-[max(0.875rem,env(safe-area-inset-top))]">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <p className="truncate text-[0.65rem] font-semibold uppercase tracking-wide text-faint">Annotatie · JAS</p>
              <h2 className="truncate font-display text-base font-semibold text-lint">{opschrift}</h2>
            </div>
            {onSluiten && (
              <button
                type="button"
                onClick={onSluiten}
                aria-label="Sluiten"
                // `-mr-1` haalt de optische ruimte van het icoon weg, zodat het kruisje uitlijnt met
                // de rechterkantlijn van de kop — hetzelfde als in `InstellingenDialog`.
                className="focus-ring -mr-1 shrink-0 rounded-kaart p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink"
              >
                {/* Zelfde icoon en lijndikte als in het instellingenvenster: één kruisje in de app,
                    niet drie die net iets anders wegen. */}
                <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                  <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
                </svg>
              </button>
            )}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            <span className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${DOCUMENT_STATUS_STYLE[doc.status]}`}>
              {DOCUMENT_STATUS_LABEL[doc.status]}
            </span>
            {/* De wettekst gaat mee naar de export: de api heeft hem niet (de graaf is de bron). */}
            <ExportKnop slug={doc.slug} leden={info.leden_teksten} onFout={setFout} />
            {onStatus && <StatusKnop status={doc.status} bezig={statusBezig} onZet={zetStatus} />}
          </div>
        </div>

        {/* Twee zones met een EIGEN scroll. Eén gedeelde scroller liet de wettekst uit beeld lopen
            zodra je verderop in de lijst kwam — precies de context die je nodig hebt om te oordelen. */}
        <div className="flex min-h-0 flex-1 flex-col overflow-hidden px-4 pt-4">
          <div className="max-h-[45%] overflow-y-auto pb-3">
          <DocumentPaneel
            opschrift=""
            regels={regels}
            // Verworpen markeringen niet in de tekst oplichten (de reviewer keurde ze net af); ze
            // blijven wél in de ReviewQueue zichtbaar met hun "verworpen"-status.
            elementen={doc.elementen
              .filter((e) => e.lifecycle !== "rejected")
              .map((e) => ({
                id: e.id, klasse: e.klasse, tekst: e.tekst, herkomst: e.herkomst, anker: e.anker,
              }))}
            actiefId={actiefId}
            onKies={onKies}
            onSelectie={onEigenMarkering && !vergrendeld ? setSelectie : undefined}
          />
          {onEigenMarkering && !vergrendeld && (
            <p className="mt-2 text-xs text-faint">
              Tip: selecteer een stuk tekst om het zelf te markeren — of klik eerst een markering aan
              en selecteer opnieuw om die in te korten of uit te breiden.
            </p>
          )}
          </div>

          {fout && (
            <div className="py-2">
              <Melding type="fout" compact>{fout}</Melding>
            </div>
          )}

          {/* Zonder deze regel lijkt een afgeronde annotatie kapot: de knoppen zijn weg en er staat
              niets over waarom. Neutraal van toon — afgerond zijn is de bedoeling, geen fout. */}
          {vergrendeld && (
            <div className="py-2">
              <Melding type="uitleg" compact>
                Deze annotatie is afgerond en staat daarom op slot. Kies <em>Heropenen</em> hierboven
                om hem weer te kunnen wijzigen.
              </Melding>
            </div>
          )}

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto py-3 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {doc.elementen.length > 0 ? (
            <ReviewQueue
              elementen={doc.elementen}
              getoond={getoond}
              filter={filter}
              onFilter={setFilter}
              actiefId={actiefId}
              zwevendeIds={zwevendeIds}
              open={open}
              onOpen={setOpen}
              onAkkoord={keurGoed}
              onKies={onKies}
              onBeslissing={beslis}
              onVerwijder={onWisEigenMarkering && !vergrendeld ? wis : undefined}
              onVraag={onVraag}
              docVergrendeld={vergrendeld}
              // Alleen als het document méér dan één lid beslaat. Is het tot één lid afgebakend, dan
              // staat dat al in de kop hierboven en herhaalt elke kaart dezelfde mededeling.
              toonLid={!doc.lid}
            />
          ) : (
            <p className="text-sm text-muted">Geen elementen.</p>
          )}
          {ontbrekend && ontbrekend.length > 0 && (
            <OntbrekendLijst
              items={ontbrekend}
              bron={bron}
              regels={regels}
              elementen={doc.elementen}
              onToevoegen={onEigenMarkering && !vergrendeld ? markeer : undefined}
            />
          )}
          </div>
        </div>

        {selectie && (
          <SelectiePopover
            doel={selectie}
            aanpasbaar={teCorrigeren ? { klasse: teCorrigeren.klasse, tekst: teCorrigeren.tekst } : undefined}
            onPasAan={teCorrigeren ? pasFragmentAan : undefined}
            onKies={markeerSelectie}
            onSluit={sluitSelectie}
          />
        )}
    </div>
  );
}


/** Afronden is een expliciete handeling van de jurist: "alle elementen beslist" is niet hetzelfde
 *  als tevreden zijn. Afronden zet de hele annotatie op slot, dus dit is óók de enige weg terug —
 *  heropenen kan altijd, want een knop die niet terug kan durft niemand te gebruiken. Bij een
 *  gepromoveerd document (in de graaf) is er niets meer te wisselen. */
function StatusKnop({
  status, bezig, onZet,
}: {
  status: DocumentStatus;
  bezig: boolean;
  onZet: (status: "geaccordeerd" | "in_review") => void;
}) {
  if (status === "gepromoveerd") return null;
  const afgerond = status === "geaccordeerd";
  return (
    <button
      type="button"
      disabled={bezig}
      onClick={() => onZet(afgerond ? "in_review" : "geaccordeerd")}
      className="focus-ring inline-flex min-h-[24px] shrink-0 items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] font-medium text-muted transition-colors hover:bg-surface hover:text-ink disabled:opacity-60 coarse:min-h-[44px] coarse:px-3"
    >
      {bezig ? "Bezig…" : afgerond ? "Heropenen" : "Annotatie afronden"}
    </button>
  );
}
