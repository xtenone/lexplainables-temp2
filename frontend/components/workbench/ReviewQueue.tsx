"use client";

import { useEffect, useRef, useState } from "react";

import { isBeslist, isVergrendeld, type ReviewFilter } from "@/lib/annotatie";
import { ChevronOmlaag, Ruit, Vinkje, Waarschuwing } from "@/components/ui/Icoon";
import { JAS_KLASSEN, jasStyle } from "@/lib/jas";
import type { AnnotatieElement, BeslissingInvoer, ReviewReason, Wijziging } from "@/lib/types";

const REDENEN: { waarde: ReviewReason; label: string }[] = [
  { waarde: "verkeerde_klasse", label: "verkeerde klasse" },
  { waarde: "bron_gemist", label: "bron gemist" },
  { waarde: "tekst", label: "tekst onjuist" },
  { waarde: "interpretatie", label: "interpretatie" },
  { waarde: "onvoldoende_context", label: "onvoldoende context" },
  { waarde: "anders", label: "anders" },
];

// Het aandacht-niveau is de dragende visuele as: het kleurt de linker-accentrand, een zachte tint en
// een badge op de kaart. Alle kleuren via de aandacht-design-tokens, geen rauwe Tailwind-kleuren
// buiten de huisstijl.
//
// Dit was een rondje van 8px zonder tekst, met de betekenis alleen in een `title`/`aria-label`. Wie
// de kleurcode niet kent zag dus een stip en verder niets — op een reviewkaart waar juist het oordeel
// van de Critic staat. Nu is het een **badge met tekst**, in dezelfde vorm als de documentstatus
// ("In behandeling", `ArtefactInhoud`): één badgevorm in de hele app.
//
// De achtergrond staat op volle sterkte terwijl de kaart eronder dezelfde tint op 40% draagt — dat
// verschil plus de rand maakt de badge zichtbaar binnen zijn eigen kleurfamilie.
const AANDACHT: Record<string, { pill: string; label: string; rand: string; tint: string }> = {
  groen: { pill: "border-aandacht-groen-rand bg-aandacht-groen-bg text-aandacht-groen-tekst", label: "Geen bezwaar", rand: "border-l-aandacht-groen-rand", tint: "bg-aandacht-groen-bg/40" },
  geel: { pill: "border-aandacht-geel-rand bg-aandacht-geel-bg text-aandacht-geel-tekst", label: "Even kijken", rand: "border-l-aandacht-geel-rand", tint: "bg-aandacht-geel-bg/40" },
  rood: { pill: "border-aandacht-rood-rand bg-aandacht-rood-bg text-aandacht-rood-tekst", label: "Waarschijnlijk fout", rand: "border-l-aandacht-rood-rand", tint: "bg-aandacht-rood-bg/40" },
};

// Zelfde vorm als de documentstatus-badge in `ArtefactInhoud`; alleen de kleuren verschillen per
// niveau. Verander je die daar, verander hem dan hier mee — het is bewust één vormtaal.
const AANDACHT_PILL =
  "inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium";

// De hoofdactie is lintblauw, net als elke andere primaire knop in de app (`ui/Button.tsx`), en de
// tweede keuze een outline. Dit was volvlak groen en volvlak hemelblauw: statuskleuren, die naast de
// gedempte tinten van een reviewkaart schreeuwen. Zo draagt de kaart alleen nog kleur waar die
// betekenis heeft — het aandacht-rondje, de JAS-badges en de rand.
const KNOP_PRIMAIR = "bg-accent text-paper hover:bg-accent-soft";
const KNOP_TWEEDE = "border border-lint bg-paper text-lint hover:bg-surface";
// Klikdoelen halen minimaal 24x24 CSS-px (WCAG 2.2 AA, 2.5.8) en groeien op aanraakschermen naar
// 44px — het AAA-niveau (2.5.5) dat NL Design System voor overheidsdiensten aanhoudt.
const KNOP_BASIS =
  "focus-ring inline-flex min-h-[24px] items-center rounded-lg px-2.5 py-1.5 text-xs font-medium " +
  "transition coarse:min-h-[44px] disabled:opacity-50";
const CHIP =
  "focus-ring inline-flex min-h-[24px] items-center rounded-full border border-line px-2.5 py-0.5 " +
  "text-[0.7rem] text-ink transition hover:border-lint hover:bg-surface coarse:min-h-[44px] disabled:opacity-50";

/** Wie dit element maakte en wat ermee gebeurde, in mensentaal.
 *
 *  De lifecycle-namen (`voorgesteld`/`critic_checked`/`edited`) zijn machinetaal; de jurist wil weten
 *  van wie het element komt en of hij er al iets mee deed. Het volledige spoor staat in het auditlog. */
function statusRegel(el: AnnotatieElement): string {
  if (el.lifecycle === "rejected") return "verworpen";
  if (el.herkomst === "mens") return "door jou gemarkeerd";
  if (el.gewijzigd_door === "mens") return "door jou aangepast";
  if (el.lifecycle === "human_approved") return "akkoord bevonden";
  return "voorstel van Lex";
}

function tijdstip(el: AnnotatieElement): string {
  const laatste = el.beslissingen[el.beslissingen.length - 1];
  if (!laatste?.tijd) return "";
  const d = new Date(laatste.tijd);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" });
}

/** Tekstveld dat zichzelf opslaat: Enter/blur bewaart, Escape annuleert.
 *
 *  Leegmaken van een gevulde waarde is óók een wijziging, maar wél een die je met één misklik maakt.
 *  Die vraagt daarom een bevestiging — de enige rem die er is, want er is geen undo. */
function InlineVeld({
  waarde,
  placeholder,
  onBewaar,
}: {
  waarde: string;
  placeholder: string;
  onBewaar: (nieuw: string) => Promise<void> | void;
}) {
  const [bewerkt, setBewerkt] = useState(false);
  const [concept, setConcept] = useState(waarde);
  const [wisBevestiging, setWisBevestiging] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (bewerkt) ref.current?.focus();
  }, [bewerkt]);

  async function bewaar() {
    const nieuw = concept.trim();
    setBewerkt(false);
    if (nieuw === waarde) return;
    if (!nieuw && waarde) {
      setWisBevestiging(true);
      return;
    }
    await onBewaar(nieuw);
  }

  if (wisBevestiging) {
    return (
      <button
        type="button"
        autoFocus
        onClick={async () => {
          setWisBevestiging(false);
          await onBewaar("");
        }}
        onBlur={() => {
          setWisBevestiging(false);
          setConcept(waarde);
        }}
        className={`${CHIP} border-fout text-fout`}
      >
        Toelichting wissen?
      </button>
    );
  }

  if (!bewerkt) {
    return (
      <button
        type="button"
        onClick={() => {
          setConcept(waarde);
          setBewerkt(true);
        }}
        className={`focus-ring min-h-[24px] w-full rounded px-1 py-0.5 text-left transition hover:bg-surface coarse:min-h-[44px] ${waarde ? "" : "text-faint"}`}
      >
        {waarde || placeholder}
      </button>
    );
  }

  return (
    <input
      ref={ref}
      value={concept}
      onChange={(e) => setConcept(e.target.value)}
      onBlur={() => void bewaar()}
      onKeyDown={(e) => {
        if (e.key === "Enter") void bewaar();
        if (e.key === "Escape") {
          setConcept(waarde);
          setBewerkt(false);
        }
      }}
      placeholder={placeholder}
      className="min-h-[24px] w-full rounded-field border border-lint bg-paper px-2 py-1 text-xs text-ink focus:outline-none coarse:min-h-[44px]"
    />
  );
}

function DecisionCard({
  el,
  actief,
  onKies,
  onBeslissing,
  onVerwijder,
  zwevend,
  open,
  onOpen,
  onAkkoord,
  onVraag,
  docVergrendeld,
  toonLid,
}: {
  el: AnnotatieElement;
  actief: boolean;
  onKies: () => void;
  onBeslissing: (req: BeslissingInvoer) => Promise<void>;
  /** Alleen bij een eigen markering: die kun je écht wissen. Weglaten verbergt de wisknop. */
  onVerwijder?: () => Promise<void>;
  /** Het fragment is niet (meer) letterlijk in de wettekst te vinden — dan valt de markering weg. */
  zwevend?: boolean;
  /** Welke bedieningsrij openstaat. Van buitenaf gestuurd zodat het toetsenbord (`c`/`x`) hem ook
   *  kan openen — en zodat er nooit twee kaarten tegelijk een rij open hebben staan. */
  open: OpenRij;
  onOpen: (rij: OpenRij) => void;
  /** Goedkeuren. Loopt langs de lijst-eigenaar zodat de knop en de `a`-toets hetzelfde doen —
   *  inclusief het doorspringen naar het volgende element dat nog aandacht vraagt. */
  onAkkoord: () => Promise<void>;
  /** Zet een vraag over dít element klaar in het centrale chatvenster. Weglaten verbergt de knop. */
  onVraag?: () => void;
  /** De hele annotatie is afgerond: dan ligt ook het opmerkingveld stil, want de api weigert élke
   *  mutatie tot het document heropend wordt. */
  docVergrendeld?: boolean;
  /** Beslaat het document meer dan één lid? Zo niet, dan staat het lid al in de kop van het artefact
   *  en herhaalt elke kaart dezelfde mededeling. */
  toonLid?: boolean;
}) {
  const [notitie, setNotitie] = useState(false);
  const palet = open === "klasse";
  const wegHalen = open === "verwerp";
  const [bezig, setBezig] = useState(false);
  const kaartRef = useRef<HTMLDivElement>(null);

  const beslist = isBeslist(el);
  // Twee sloten met een verschillend bereik: een eindoordeel op dít element bevriest de inhoud maar
  // laat een kanttekening toe; een afgerond document bevriest alles. `slot` is wat de bediening
  // uitschakelt, `elVergrendeld` is wat de Heropenen-knop tevoorschijn haalt.
  const elVergrendeld = isVergrendeld(el);
  const slot = elVergrendeld || !!docVergrendeld;
  const aandacht = el.aandacht ? AANDACHT[el.aandacht] : null;
  const eigen = el.herkomst === "mens";
  // Alleen de kaart waaraan je werkt toont zijn details. Alles altijd tonen kostte drie kaarten per
  // scherm; zo passen er tien in en blijft de lijst te overzien.
  const uitgeklapt = actief;

  // Klik je een markering in de tekst aan, dan hoort de bijbehorende kaart in beeld te komen — de
  // tegenhanger van het in beeld scrollen van de markering in `DocumentPaneel`.
  useEffect(() => {
    if (!actief || !kaartRef.current) return;
    const rustig = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    kaartRef.current.scrollIntoView({ block: "nearest", behavior: rustig ? "auto" : "smooth" });
  }, [actief]);

  // Selectie kwijt? Dan ook het opmerkingveld dicht. Tijdens het renderen bijstellen (het
  // gedocumenteerde React-patroon voor "state afstemmen op een gewijzigde prop") in plaats van in een
  // effect: zo is er geen tussenframe met een open veld op een kaart waar je niet meer aan werkt.
  const [vorigActief, setVorigActief] = useState(actief);
  if (vorigActief !== actief) {
    setVorigActief(actief);
    if (!actief) setNotitie(false);
  }

  async function verstuur(req: BeslissingInvoer) {
    setBezig(true);
    try {
      await onBeslissing(req);
      onOpen("geen");
    } catch {
      // De melding staat al boven de lijst (het artefact vangt hem); hier alleen zorgen dat de kaart
      // uit zijn bezig-stand komt en de rij open blijft, zodat je het opnieuw kunt proberen.
    } finally {
      setBezig(false);
    }
  }

  /** Open een bedieningsrij op DEZE kaart.
   *
   *  De rij hangt aan de actieve kaart (`open={el.id === actiefId ? … : "geen"}`), en de knoppen
   *  stoppen hun klik zodat de kaart-onClick niet ook nog vuurt. Gevolg: op een niet-actieve kaart
   *  gebeurde er zichtbaar niets — en klapte het palet open op de kaart die wél actief was. Eerst
   *  selecteren dus. Alleen als de kaart het nog niet is: `onKies` is een toggle, en op de actieve
   *  kaart zou hij de selectie juist opheffen.
   */
  function openRij(rij: OpenRij) {
    if (!actief) onKies();
    onOpen(rij);
  }

  /** Eén wijziging wegschrijven — geen dropdown, geen opslaan-knop.
   *
   *  De `review_reason` gaat niet mee: die leidt de server af uit de diff die hij zelf berekent.
   *  Hij werd hier vroeger meegestuurd, maar een reden die de server niet kan toetsen hoort niet in
   *  een auditspoor. Bij verwerpen blijft de reden wél een vraag aan de jurist — die informatie
   *  staat in geen enkele diff.
   */
  async function wijzig(w: Wijziging) {
    await verstuur({ type: "edit", wijziging: w });
  }

  return (
    <div
      ref={kaartRef}
      onClick={onKies}
      className={`rounded-kaart border border-line border-l-4 bg-paper p-3 shadow-zacht transition ${
        beslist ? "opacity-75" : aandacht ? `${aandacht.rand} ${aandacht.tint}` : "border-l-line"
      } ${actief ? "border-lint ring-1 ring-lint" : ""}`}
    >
      {/* De kop in twee lagen, en op `sm:` weer op één regel.
          Alles vocht eerder om dezelfde regel: een lange klassenaam ("Parameter en parameterwaarde")
          duwde het lidnummer naar een eigen regel en perste Akkoord en het kruisje tegen de kaartrand.
          Nu staan links de korte, voorspelbare dingen (aandacht, lid) mét de acties, en krijgt de
          klassebadge daaronder de volle breedte. Op een breed scherm past het weer naast elkaar —
          hetzelfde patroon als `ui/ButtonRow`: mobiel gestapeld, `sm:` naast elkaar. */}
      <div className="flex flex-wrap items-center gap-1.5 sm:flex-nowrap sm:items-start sm:gap-2">
        {/* `min-w-0`: zonder dit rekt een brede klassenaam deze kant alsnog op. */}
        <span className="order-1 flex min-w-0 flex-wrap items-center gap-1.5">
          {el.aandacht && aandacht && (
            <span className={`${AANDACHT_PILL} ${aandacht.pill}`} title={el.critic || undefined}>
              {aandacht.label}
            </span>
          )}
          {/* Twijfel is geen bezwaar: de annoteerder zag twee plausibele klassen. Eerder werd zoiets
              automatisch geel, waardoor een écht aandachtspunt niet meer opviel tussen de
              disambiguaties. Neutraal merkje dus, geen kleur uit de aandacht-as. */}
          {!el.aandacht && el.alternatieven.length > 0 && (
            <span role="img" title="Twijfel tussen klassen — zie de alternatieven" aria-label="twijfel"
                  className="text-xs text-muted"><Ruit /></span>
          )}
          {/* Het lid alleen als het document méér dan één lid beslaat; anders staat het al in de kop
              van het artefact ("artikel 9 lid 1") en herhaalt elke kaart dezelfde mededeling. */}
          {toonLid && el.lid && <span className="text-[0.65rem] text-muted">lid {el.lid}</span>}
        </span>

        {/* De klasse ís de knop: klikken opent het palet, klikken op een klasse is de wijziging.
            Op slot is het geen knop meer maar een badge — géén `disabled` knop, want die leest als
            "tijdelijk kapot" terwijl er niets kapot is; er is alleen eerst iets anders nodig. */}
        {/* `w-full` op mobiel dwingt de wrap: de klasse krijgt zo een eigen regel ónder de meta en de
            acties. Op `sm:` valt dat weg en schuift hij ertussen. */}
        <span className="order-3 flex w-full min-w-0 sm:order-2 sm:w-auto sm:flex-1">
          {slot ? (
            <span
              className={`inline-flex min-h-[24px] max-w-full items-center whitespace-normal rounded px-2 py-0.5 text-left text-xs font-semibold leading-tight ${jasStyle(el.klasse)}`}
            >
              {el.klasse}
            </span>
          ) : (
            <button
              type="button"
              disabled={bezig}
              onClick={(e) => {
                e.stopPropagation();
                openRij(palet ? "geen" : "klasse");
              }}
              title="Andere klasse kiezen"
              className={`focus-ring inline-flex min-h-[24px] max-w-full items-center whitespace-normal rounded px-2 py-0.5 text-left text-xs font-semibold leading-tight transition hover:ring-1 hover:ring-lint coarse:min-h-[44px] disabled:opacity-50 ${jasStyle(el.klasse)}`}
            >
              {el.klasse} <ChevronOmlaag className="ml-0.5 shrink-0 opacity-70" />
            </button>
          )}
        </span>

        {/* `ml-auto` duwt de acties op mobiel naar rechts op dezelfde regel als de aandacht-badge;
            op `sm:` doet de flex-verdeling dat al. */}
        <span
          className="order-2 ml-auto flex shrink-0 items-center gap-1 sm:order-3 sm:ml-0"
          onClick={(e) => e.stopPropagation()}
        >
          {!slot && (
            <button
              type="button"
              disabled={bezig}
              onClick={async () => {
                setBezig(true);
                try {
                  await onAkkoord();
                } catch {
                  /* de melding staat boven de lijst */
                } finally {
                  setBezig(false);
                }
              }}
              className={`${KNOP_BASIS} ${KNOP_PRIMAIR}`}
            >
              Akkoord
            </button>
          )}
          {/* De weg terug. Zonder deze knop is een akkoord een doodlopende weg: de bediening ligt
              stil en er is niets dat hem weer aanzet. Tweede keuze qua vorm — heropenen is een
              correctie, geen hoofdactie. */}
          {elVergrendeld && !docVergrendeld && (
            <button
              type="button"
              disabled={bezig}
              onClick={() => void verstuur({ type: "heropen" })}
              title="Terugzetten in de review, zodat je hem weer kunt wijzigen"
              className={`${KNOP_BASIS} ${KNOP_TWEEDE}`}
            >
              Heropenen
            </button>
          )}
          {!slot && (!beslist || eigen) && (
            <button
              type="button"
              disabled={bezig}
              onClick={() => openRij(wegHalen ? "geen" : "verwerp")}
              aria-label={eigen ? "Markering wissen" : "Voorstel verwerpen"}
              title={eigen ? "Wissen" : "Verwerpen"}
              className="focus-ring inline-flex min-h-[24px] min-w-[24px] items-center justify-center rounded-lg p-1.5 text-muted transition hover:bg-surface hover:text-fout coarse:min-h-[44px] coarse:min-w-[44px]"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          )}
        </span>
      </div>

      {palet && !slot && (
        <div className="mt-2 flex flex-wrap gap-1" onClick={(e) => e.stopPropagation()}>
          {JAS_KLASSEN.filter((k) => k !== el.klasse).map((k) => (
            <button
              key={k}
              type="button"
              disabled={bezig}
              onClick={() => void wijzig({ klasse: k })}
              className={`focus-ring inline-flex min-h-[28px] items-center rounded-full border px-2 py-0.5 text-xs transition coarse:min-h-[44px] disabled:opacity-50 ${jasStyle(k)}`}
            >
              {k}
            </button>
          ))}
        </div>
      )}

      {/* Wissen (eigen markering) of verwerpen (agent-voorstel): hetzelfde gebaar, twee uitkomsten.
          Wissen is onomkeerbaar — vandaar de tweede klik in plaats van een dialoog. Bij verwerpen is
          de reden echte informatie die alleen de mens heeft; die is niet af te leiden. */}
      {wegHalen && !slot && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
          {eigen ? (
            <button
              type="button"
              disabled={bezig || !onVerwijder}
              onClick={async () => {
                setBezig(true);
                try {
                  await onVerwijder?.();
                } catch {
                  /* de melding staat boven de lijst */
                } finally {
                  setBezig(false);
                  onOpen("geen");
                }
              }}
              className={`${CHIP} border-fout font-medium text-fout`}
            >
              Wissen?
            </button>
          ) : (
            <>
              <span className="text-[0.7rem] text-muted">Verwerpen — waarom?</span>
              {REDENEN.map((r) => (
                <button
                  key={r.waarde}
                  type="button"
                  disabled={bezig}
                  onClick={() => void verstuur({ type: "reject", review_reason: r.waarde })}
                  className={CHIP}
                >
                  {r.label}
                </button>
              ))}
            </>
          )}
        </div>
      )}

      <p className="mt-2 border-l-2 border-line pl-2.5 text-sm italic text-ink">“{el.tekst}”</p>

      {/* Een markering die niet in de tekst te vinden is verdween eerder stilzwijgend uit de
          weergave. Dan lijkt hij weg terwijl hij er nog is — zeg het gewoon. */}
      {zwevend && (
        <p className="mt-1.5 flex items-center gap-1 text-xs text-aandacht-geel-tekst">
          <Waarschuwing /> Niet terug te vinden in de tekst — pas het fragment aan of
          verwerp de markering.
        </p>
      )}

      {uitgeklapt && (
        <div className="mt-1.5 text-xs text-muted" onClick={(e) => e.stopPropagation()}>
          {slot ? (
            el.toelichting && <p className="px-1 py-0.5">{el.toelichting}</p>
          ) : (
            <InlineVeld
              waarde={el.toelichting}
              placeholder="Toelichting toevoegen…"
              onBewaar={(nieuw) => wijzig({ toelichting: nieuw })}
            />
          )}
        </div>
      )}

      {uitgeklapt && el.critic && <p className="mt-1 text-xs italic text-muted">Critic: {el.critic}</p>}

      {/* Het heen-en-weer met de Critic. Pas vanaf twee rondes: bij één ronde staat het oordeel
          hierboven al en zou dit hetzelfde twee keer zeggen. */}
      {uitgeklapt && el.critic_rondes.length > 1 && (
        <ol className="mt-1.5 space-y-0.5 border-l-2 border-line pl-2.5 text-[0.7rem] text-muted">
          {el.critic_rondes.map((r) => (
            <li key={r.ronde}>
              <span className="font-medium">Ronde {r.ronde}</span>
              {r.aandacht ? ` · ${r.aandacht}` : ""}
              {r.actie && r.actie !== "behoud" ? ` · ${r.actie}` : ""}
              {r.voorstel_klasse ? ` → ${r.voorstel_klasse}` : ""}
              {/* Een voorstel dat is uitgevoerd leest anders dan een voorstel dat bleef liggen. */}
              {r.toegepast ? " · toegepast" : ""}
              {r.motivatie ? ` — ${r.motivatie}` : ""}
            </li>
          ))}
        </ol>
      )}

      {/* Kanttekening bij een markering die de JURIST zelf maakte. Bewust een andere vorm dan de kaart
          zelf: dit is advies dat je naast je neer mag leggen, geen voorstel om te beoordelen. */}
      {/* Een openstaande kanttekening blijft ook ingeklapt zichtbaar: dat signaal mag je niet missen
          doordat het achter een selectie verstopt zit. */}
      {!uitgeklapt && el.critic_suggestie?.motivatie && el.critic_suggestie.status === "open" && (
        <p className="mt-1.5 truncate text-xs text-muted">
          <span className="font-medium text-ink">Kanttekening:</span> {el.critic_suggestie.motivatie}
        </p>
      )}

      {uitgeklapt && !slot && el.critic_suggestie?.motivatie && el.critic_suggestie.status === "open" && (
        <div
          className="mt-2 rounded-kaart border border-dashed border-line bg-surface p-2"
          onClick={(e) => e.stopPropagation()}
        >
          <p className="text-xs text-muted">
            <span className="font-medium text-ink">Kanttekening van Lex:</span>{" "}
            {el.critic_suggestie.motivatie}
            {el.critic_suggestie.voorstel_klasse && (
              <> Voorstel: <span className={`rounded px-1 ${jasStyle(el.critic_suggestie.voorstel_klasse)}`}>
                {el.critic_suggestie.voorstel_klasse}
              </span></>
            )}
            {el.critic_suggestie.voorstel_tekst && (
              <> Voorgesteld fragment: <q className="italic">{el.critic_suggestie.voorstel_tekst}</q></>
            )}
          </p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {el.critic_suggestie.voorstel_klasse && (
              <button
                disabled={bezig}
                onClick={() => void wijzig({ klasse: el.critic_suggestie!.voorstel_klasse })}
                className={`${KNOP_BASIS} ${KNOP_PRIMAIR}`}
              >
                Overnemen
              </button>
            )}
            {/* Zonder anker: de server wist het oude dan, want dat wees naar het fragment zoals het
                wás. Zie `Wijziging.anker`. */}
            {el.critic_suggestie.voorstel_tekst && (
              <button
                disabled={bezig}
                onClick={() => void wijzig({ tekst: el.critic_suggestie!.voorstel_tekst })}
                className={`${KNOP_BASIS} ${KNOP_PRIMAIR}`}
              >
                Fragment overnemen
              </button>
            )}
            <button
              disabled={bezig}
              onClick={() =>
                void verstuur({ type: "comment", comment: "Kanttekening van Lex afgewezen." })
              }
              className={`${KNOP_BASIS} ${KNOP_TWEEDE}`}
            >
              Naast me neerleggen
            </button>
          </div>
        </div>
      )}

      {uitgeklapt && !slot && el.alternatieven.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1 text-xs text-muted" onClick={(e) => e.stopPropagation()}>
          <span>Twijfel — klik om te wisselen:</span>
          {el.alternatieven.map((a) => (
            <button
              key={a.klasse}
              disabled={bezig}
              title={a.motivatie}
              onClick={() => void wijzig({ klasse: a.klasse })}
              className={`focus-ring inline-flex min-h-[24px] items-center rounded px-1.5 py-0.5 text-xs font-medium coarse:min-h-[44px] ${jasStyle(a.klasse)} hover:ring-1 hover:ring-lint`}
            >
              {a.klasse}
            </button>
          ))}
        </div>
      )}

      {/* Vragen doe je in het centrale gespreksvenster, niet in een tweede chatje hier. Deze knop zet
          de vraag daar klaar mét de context van dit element; het antwoord komt in de thread — inclusief
          bronnen en grounding, die een draadje in de kaart nooit toonde. */}
      {uitgeklapt && onVraag && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onVraag();
          }}
          className="focus-ring mt-2 inline-flex min-h-[24px] items-center gap-1.5 rounded-lg border border-line px-2 py-1 text-xs text-lint transition hover:border-lint hover:bg-surface coarse:min-h-[44px]"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Vraag Lex
        </button>
      )}

      <div className="mt-2 flex items-center justify-between gap-2 border-t border-line/60 pt-1.5 text-[0.65rem] text-muted">
        <span className="min-w-0 flex-1" onClick={(e) => e.stopPropagation()}>
          {!uitgeklapt || docVergrendeld ? null : notitie ? (
            <InlineVeld
              waarde=""
              placeholder="Opmerking bij de review…"
              onBewaar={async (tekst) => {
                if (tekst) await verstuur({ type: "comment", comment: tekst });
                setNotitie(false);
              }}
            />
          ) : (
            <button
              type="button"
              onClick={() => setNotitie(true)}
              className="focus-ring inline-flex min-h-[24px] items-center rounded underline-offset-2 hover:underline coarse:min-h-[44px]"
            >
              Opmerking…
            </button>
          )}
        </span>
        <span className="shrink-0">
          {statusRegel(el)}
          {tijdstip(el) && ` · ${tijdstip(el)}`}
        </span>
      </div>
    </div>
  );
}

/** Welke bedieningsrij op de actieve kaart openstaat. */
export type OpenRij = "geen" | "klasse" | "verwerp";

const FILTERS: { waarde: ReviewFilter; label: string }[] = [
  { waarde: "alles", label: "Alles" },
  { waarde: "te_beoordelen", label: "Te beoordelen" },
  { waarde: "aandacht", label: "Met aandacht" },
];

export function ReviewQueue({
  elementen,
  getoond,
  filter,
  onFilter,
  actiefId,
  zwevendeIds,
  open,
  onOpen,
  onAkkoord,
  onKies,
  onBeslissing,
  onVerwijder,
  onVraag,
  docVergrendeld,
  toonLid,
}: {
  /** Alle elementen — voor de tellingen in de kop. */
  elementen: AnnotatieElement[];
  /** De gesorteerde, gefilterde lijst zoals hij getoond wordt. Komt van buiten zodat het toetsenbord
   *  precies dezelfde volgorde doorloopt als je ziet. */
  getoond: AnnotatieElement[];
  filter: ReviewFilter;
  onFilter: (f: ReviewFilter) => void;
  actiefId?: string;
  /** Elementen waarvan het fragment niet in de wettekst te vinden is (berekend door het artefact). */
  zwevendeIds?: Set<string>;
  open: OpenRij;
  onOpen: (rij: OpenRij) => void;
  onAkkoord: (elementId: string) => Promise<void>;
  onKies: (id?: string) => void;
  onBeslissing: (elementId: string, req: BeslissingInvoer) => Promise<void>;
  /** Eigen markering wissen. Weglaten maakt de lijst alleen-beoordeelbaar. */
  onVerwijder?: (elementId: string) => Promise<void>;
  /** Zet een vraag over een element klaar in het centrale chatvenster. */
  onVraag?: (el: AnnotatieElement) => void;
  /** De annotatie is afgerond: de hele lijst staat op slot tot hij heropend wordt. */
  docVergrendeld?: boolean;
  /** Zie `Kaart`: alleen tonen als het document meer dan één lid beslaat. */
  toonLid?: boolean;
}) {
  const totaal = elementen.length;
  const beslist = elementen.filter(isBeslist).length;
  const teReviewen = totaal - beslist;
  const metAandacht = elementen.filter((el) => el.aandacht === "rood" || el.aandacht === "geel").length;
  const zwevend = zwevendeIds?.size ?? 0;
  const perc = totaal ? Math.round((beslist / totaal) * 100) : 0;
  const afgerond = totaal > 0 && beslist === totaal;

  return (
    <div className="space-y-2.5">
      {/* Voortgang: hoeveel van de N elementen zijn beoordeeld, met een dunne balk. */}
      <div className="rounded-kaart border border-line bg-surface px-3 py-2.5 shadow-zacht">
        <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
          <span className="text-xs font-medium text-ink">
            Review — {beslist}/{totaal} beoordeeld
          </span>
          {afgerond ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-aandacht-groen-bg px-2 py-0.5 text-[0.65rem] font-semibold text-aandacht-groen-tekst">
              <Vinkje /> Review afgerond
            </span>
          ) : (
            <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[0.65rem] text-muted">
              {teReviewen > 0 && <span>{teReviewen} te gaan</span>}
              {zwevend > 0 && (
                <span className="inline-flex items-center gap-1 text-aandacht-geel-tekst">
                  <Waarschuwing /> {zwevend} niet in de tekst
                </span>
              )}
            </span>
          )}
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-line/60" role="progressbar" aria-valuenow={perc} aria-valuemin={0} aria-valuemax={100}>
          <div className={`h-full rounded-full transition-all ${afgerond ? "bg-succes" : "bg-lint"}`} style={{ width: `${perc}%` }} />
        </div>

        {/* Drie knoppen in plaats van een dropdown: bij drie standen is kiezen sneller dan uitklappen. */}
        <div className="mt-2.5 flex flex-wrap gap-1" role="group" aria-label="Filter de reviewlijst">
          {FILTERS.map((f) => {
            const aantal =
              f.waarde === "alles" ? totaal : f.waarde === "te_beoordelen" ? teReviewen : metAandacht;
            return (
              <button
                key={f.waarde}
                type="button"
                aria-pressed={filter === f.waarde}
                onClick={() => onFilter(f.waarde)}
                className={`focus-ring min-h-[24px] rounded-full border px-2.5 py-0.5 text-[0.7rem] transition coarse:min-h-[44px] ${
                  filter === f.waarde
                    ? "border-lint bg-lint text-paper"
                    : "border-line text-muted hover:border-lint hover:text-ink"
                }`}
              >
                {f.label} ({aantal})
              </button>
            );
          })}
        </div>

        <p className="mt-2 text-[0.65rem] text-faint">
          {docVergrendeld ? (
            <>Sneltoetsen: <kbd>j</kbd>/<kbd>k</kbd> volgende · <kbd>Esc</kbd> loslaten</>
          ) : (
            <>
              Sneltoetsen: <kbd>j</kbd>/<kbd>k</kbd> volgende · <kbd>a</kbd> akkoord · <kbd>x</kbd> verwerpen
              · <kbd>c</kbd> klasse · <kbd>Esc</kbd> loslaten
            </>
          )}
        </p>
      </div>

      {getoond.length === 0 && (
        <p className="rounded-kaart border border-dashed border-line px-3 py-4 text-center text-xs text-muted">
          Geen elementen in deze selectie.
        </p>
      )}

      {getoond.map((el) => (
        <DecisionCard
          key={el.id}
          el={el}
          actief={el.id === actiefId}
          zwevend={zwevendeIds?.has(el.id)}
          open={el.id === actiefId ? open : "geen"}
          onOpen={onOpen}
          onAkkoord={() => onAkkoord(el.id)}
          onKies={() => onKies(el.id)}
          onBeslissing={(req) => onBeslissing(el.id, req)}
          onVerwijder={onVerwijder && el.herkomst === "mens" ? () => onVerwijder(el.id) : undefined}
          onVraag={onVraag ? () => onVraag(el) : undefined}
          docVergrendeld={docVergrendeld}
          toonLid={toonLid}
        />
      ))}
    </div>
  );
}
