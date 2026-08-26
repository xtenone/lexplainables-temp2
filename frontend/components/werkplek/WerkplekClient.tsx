"use client";

import Link from "next/link";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { ArtefactPaneel } from "@/components/werkplek/ArtefactPaneel";
import { Melding } from "@/components/ui/Melding";
import { Markdown, StreamendeTekst } from "@/components/werkplek/Markdown";
import {
  beslis,
  foutTekst,
  haalActieveRun,
  startRun,
  stopRun,
  volgRun,
  haalArtikelGraaf,
  haalDocument,
  haalGesprek,
  isApiError,
  maakGesprek,
  voegBerichtToe,
  verwijderElement,
  zetDocumentStatus,
  voegElementToe,
} from "@/lib/api";
import type {
  Anker,
  AnnotatieElement,
  AgentDoel,
  AgentGrounding,
  AgentDoelInvoer,
  AgentKandidaat,
  AgentRun,
  AnnotatieDocument,
  BeslissingInvoer,
  Bron,
  GraafArtikel,
  OntbrekendItem,
  VoorstelElement,
} from "@/lib/types";
import {
  annotatieTitel, BESLIST_LIFECYCLES, eigenMarkeringenVoorContext, isVerwijderd, kandidaatLabel,
  doelVanKandidaat, kandidaatPrompt, kandidatenAlsTekst, mergeVoorstellen, vraagContextLabel,
  vraagContextVan, vraagSuggesties,
} from "@/lib/annotatie";
import {
  definitieveStroomfout, herstelWachttijd, leesLopendeRuns, naEenGebrokenStream, onthoudRun,
  schrijfLopendeRuns, standVanVorigeRun, vergeetRun, wachtMetWekker,
} from "@/lib/lopendeRun";
import { useBreedScherm } from "@/lib/useBreedScherm";
import { ChevronOmlaag, Cirkel, Waarschuwing } from "@/components/ui/Icoon";
import { jasStyle } from "@/lib/jas";
import { bronHref } from "@/lib/url";

type Item =
  | { id: string; type: "user"; tekst: string; over?: string }
  | { id: string; type: "antwoord"; tekst: string; denk?: string; bronnen?: Bron[];
      // De brongetrouwheidstoets van déze beurt. Live; hij reist niet mee in het berichtcontract,
      // maar de statusregel ervan staat wél in `denk` en blijft dus na herladen terug te vinden.
      grounding?: AgentGrounding }
  // `denk` = de tijdlijn van het samenspel (supervisor → ophaal → annoteerder ⇄ Critic). Die werd
  // eerder weggegooid zodra de beurt een annotatie bleek; juist bij een annotatie wil je achteraf
  // kunnen zien hoe hij tot stand kwam.
  // `titel` komt uit het bericht zelf (`annotatie_titel`), niet uit het document: er is geen foreign
  // key, dus na het verwijderen van het document is dit het enige dat de kaart nog kan benoemen.
  | { id: string; type: "annotatie"; slug: string; titel?: string; ontbrekend?: OntbrekendItem[]; denk?: string }
  // De vraag noemde een onderwerp: de agent vond bepalingen, de jurist kiest er één.
  | { id: string; type: "kandidaten"; tekst: string; kandidaten: AgentKandidaat[] };

/** Wat er zojuist is vastgelegd, in één zin voor de schermlezer. */
function beslissingMelding(req: BeslissingInvoer): string {
  if (req.type === "approve") return "Akkoord bevonden.";
  if (req.type === "reject") return "Verworpen.";
  if (req.type === "comment") return "Opmerking opgeslagen.";
  const w = req.wijziging ?? {};
  if (w.klasse) return `Klasse gewijzigd naar ${w.klasse}.`;
  if (w.tekst) return `Fragment aangepast naar ${w.tekst}.`;
  if (w.toelichting !== undefined) return w.toelichting ? "Toelichting opgeslagen." : "Toelichting gewist.";
  return "Wijziging opgeslagen.";
}

/** Hoeveel elementen wachten nog op een oordeel? Zelfde regel als de reviewlijst. */
function teBeoordelen(doc: AnnotatieDocument): number {
  return doc.elementen.filter((el) => !BESLIST_LIFECYCLES.includes(el.lifecycle)).length;
}

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/** Is dit een door onszelf afgebroken stream, of een echte fout? */
function isAfgebroken(e: unknown): boolean {
  return (e as Error)?.name === "AbortError";
}

// Opnieuw aanhaken bij een weggevallen verbinding gebeurt zolang dit venster leeft, met een
// oplopende wachttijd (`herstelWachttijd`) en een banner die zegt wat er aan de hand is. De regel
// zelf staat in `lib/lopendeRun.ts`; hier staat alleen wat het scherm ermee doet.
//
// Dit was eerder één poging na 1,5 seconde. Duurde de onderbreking langer — een herstart van
// graph-qa is dat al — dan kwam de beurt als mislukt in beeld terwijl hij gewoon doorliep, en
// alleen een herlaadbeurt bracht hem terug.

interface Props {
  /** Het te openen gesprek, of `null` voor een vers (nog niet gepersisteerd) gesprek. */
  initialGesprekId: string | null;
  /** Roept terug zodra bij de eerste beurt een gesprek is aangemaakt (voor sidebar-highlight + lijst). */
  onGesprekAangemaakt: (id: string) => void;
  /** Roept terug na elke persistente wijziging zodat de sidebar-lijst kan verversen. */
  onGewijzigd: () => void;
  /** Annotatie die bij binnenkomst open moet staan (deep-link vanuit het annotatie-overzicht). */
  beginArtefact?: string;
}

export function WerkplekClient({
  initialGesprekId, onGesprekAangemaakt, onGewijzigd, beginArtefact,
}: Props) {
  const [gesprekId, setGesprekId] = useState<string | null>(initialGesprekId);
  const [items, setItems] = useState<Item[]>([]);
  const [docs, setDocs] = useState<Record<string, AnnotatieDocument>>({});
  const [infos, setInfos] = useState<Record<string, GraafArtikel>>({});
  // Slugs waarvan de api 404 gaf: het document bestaat niet meer. Dat is een tóéstand, geen fout —
  // opnieuw proberen kan per definitie niet lukken. Apart van `docs` omdat "nog niet geladen" en
  // "bestaat niet meer" twee verschillende dingen zijn.
  const [verwijderd, setVerwijderd] = useState<Record<string, true>>({});
  const [invoer, setInvoer] = useState("");
  // Niet-blokkerende melding als het opslaan van een beurt faalt (de chat loopt door).
  const [bewaarFout, setBewaarFout] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);
  const [actiefId, setActiefId] = useState<string | undefined>();
  const [artefactSlug, setArtefactSlug] = useState<string | undefined>();
  // Zichtbaarheid van de "naar beneden"-pil: aan zodra de gebruiker weg van de bodem scrolt.
  const [toonNaarBeneden, setToonNaarBeneden] = useState(false);
  // Wat er zojuist is opgeslagen, voor schermlezers. Zonder dit gebeurt elke annotatie-wijziging
  // volledig stil: de kaart verandert visueel, maar er wordt niets aangekondigd.
  const [melding, setMelding] = useState("");
  // Waar de volgende vraag over gaat, gezet vanuit een reviewkaart. Zolang dit staat gaat de beurt
  // als adviesvraag (met contextblok) in plaats van als gewone vraag.
  const [vraagOver, setVraagOver] = useState<{ slug: string; el: AnnotatieElement } | null>(null);
  // De run die nu loopt. Die leeft bij de agent, niet in dit venster: dit id is waarmee we
  // aanhaken en waarmee de stopknop hem beëindigt.
  const [runId, setRunId] = useState<string | null>(null);
  // Stoppen is gevraagd maar nog niet gebeurd. De agent-nodes zijn synchroon, dus een lopende
  // LLM-call maakt zichzelf af — dat kan tientallen seconden duren en de knop hoort dat te tonen
  // in plaats van te doen alsof het al klaar is.
  const [stopt, setStopt] = useState(false);
  // Het artefact openen haalt document + wettekst op. Dat mag niet stil gebeuren: zonder deze twee
  // leverde een mislukte graaf-call een klik op waar lettérlijk niets van gebeurde.
  const [artefactLaadt, setArtefactLaadt] = useState<string | null>(null);
  const [artefactFout, setArtefactFout] = useState<{ slug: string; melding: string } | null>(null);
  // Zojuist geprobeerd te openen, maar het document bestaat niet meer. Los van `artefactFout`, want
  // dit is geen storing: geen rode balk en geen retry. Nodig naast de tombstone-kaart omdat een
  // deep-link (`/workbench?annotatie=…`) helemaal geen kaart in de thread hoeft te hebben.
  const [artefactWeg, setArtefactWeg] = useState<string | null>(null);
  // De vorige beurt van dit gesprek is nooit afgekomen: het run-register van de agent is leeg (een
  // herstart of deploy). Beter dit zeggen dan een gesprek dat halverwege ophoudt zonder uitleg.
  const [runVerdwenen, setRunVerdwenen] = useState(false);
  // De verbinding met de lopende beurt is weg en we haken opnieuw aan. Een tóéstand en geen tekst in
  // de antwoordbubbel: alleen zo kan de melding vanzelf verdwijnen zodra de stroom weer loopt — wat
  // hij eerder niet deed, zodat er niets anders op zat dan herladen.
  const [verbindingWeg, setVerbindingWeg] = useState(false);
  const lijstRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  // Synchrone guard tegen dubbel-verzenden (twee Enters in dezelfde tick): de `bezig`-state komt te laat
  // — vóór de eerste `await` (maakGesprek) is die nog false, wat twee gesprekken zou aanmaken.
  const bezigRef = useRef(false);
  // Waarmee een lopende beurt is af te breken. Een annotatie duurt tot ~90 seconden; zonder dit is
  // een verkeerd gestelde vraag anderhalve minuut wachten.
  const afbrekenRef = useRef<AbortController | null>(null);
  // "Stick-to-bottom": alleen automatisch meescrollen als de gebruiker al onderaan staat, zodat
  // omhoogscrollen tijdens het streamen niet telkens wordt teruggetrokken.
  const stickRef = useRef(true);
  // Leeft dit venster nog? De unmount-cleanup aborteert `afbrekenRef`, maar een aanhaakactie die ná
  // die cleanup zijn controller zet, wordt door niets meer opgeruimd — en laat dan een SSE-stroom
  // open staan voor een scherm dat niemand ziet.
  const levendRef = useRef(true);
  // Past het artefact naast de chat? Dan wordt het een eigen kolom in plaats van een overlay, en
  // blijft Lex bereikbaar tijdens het reviewen.
  const breed = useBreedScherm();

  // Verdwijnt dit venster (van gesprek wisselen remount het component), dan koppelen we alleen de
  // KIJKER los. De run zelf draait bij de agent door en wordt opgepakt zodra je terugkomt.
  //
  // Dit stond hier eerder als `abort()` op de beurt zelf, en dat was de oorzaak van "vragen worden
  // afgebroken": van gesprek wisselen, naar het annotatie-overzicht lopen of herladen doodde het
  // antwoord waar je op wachtte. Stoppen is nu een expliciete handeling (`stop()`), geen bijwerking
  // van navigeren.
  useEffect(() => {
    levendRef.current = true;
    return () => {
      levendRef.current = false;
      afbrekenRef.current?.abort();
    };
  }, []);

  // Hydrateer één keer bij mount: bestaande gespreksberichten → thread. Lees de id uit een MOUNT-vaste
  // ref, niet uit de reactieve prop: bij de eerste beurt zet de shell `activeId` (→ prop null→id) zónder
  // remount; zou de effect daarop herstarten, dan overschrijft `haalGesprek` de lopende stream. Een échte
  // gespreks-wissel remount dit component (via `key={mountKey}`), dus de ref draagt dan de juiste id.
  const hydratieId = useRef(initialGesprekId).current;
  useEffect(() => {
    if (!hydratieId) return;
    let afgebroken = false;
    haalGesprek(hydratieId)
      .then((g) => {
        if (afgebroken) return;
        setItems(
          g.berichten.map((b) =>
            b.rol === "user"
              ? { id: uid(), type: "user" as const, tekst: b.tekst }
              : b.annotatie_slug
                ? { id: uid(), type: "annotatie" as const, slug: b.annotatie_slug,
                    titel: b.annotatie_titel || undefined, ontbrekend: b.ontbrekend, denk: b.denk }
                : { id: uid(), type: "antwoord" as const, tekst: b.tekst, denk: b.denk, bronnen: b.bronnen },
          ),
        );
        // Documenten van annotatie-berichten alvast laden voor de chip-labels.
        for (const b of g.berichten) if (b.annotatie_slug) void laadDoc(b.annotatie_slug);
        // Liep hier nog een beurt terwijl je ergens anders keek? Pak hem weer op. De run-ids uit de
        // geschiedenis gaan mee: daarmee is "afgerond terwijl je weg was" te onderscheiden van
        // "weg door een herstart".
        void hervatBeurt(hydratieId, g.berichten.map((b) => b.run_id).filter(Boolean));
      })
      .catch(() => {});
    return () => {
      afgebroken = true;
    };
    // `laadDoc` bewust niet als dependency: deze hydratatie hoort één keer per mount te draaien (zie
    // de toelichting hierboven), en de functie wordt elke render opnieuw gemaakt.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydratieId]);

  useEffect(() => {
    const el = lijstRef.current;
    if (el && stickRef.current) el.scrollTo({ top: el.scrollHeight });
  }, [items, bezig]);

  function onThreadScroll() {
    const el = lijstRef.current;
    if (!el) return;
    const bijBodem = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    stickRef.current = bijBodem;
    setToonNaarBeneden(!bijBodem && items.length > 0); // React bail-out bij gelijke waarde
  }

  function naarBeneden() {
    const el = lijstRef.current;
    if (!el) return;
    stickRef.current = true;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    setToonNaarBeneden(false);
  }

  // Auto-groeiende textarea (groeit met de inhoud tot een max; daarna intern scrollen).
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [invoer]);

  function updateItem(id: string, patch: Partial<Item>) {
    setItems((xs) => xs.map((x) => (x.id === id ? ({ ...x, ...patch } as Item) : x)));
  }

  /** Haalt het document op en cachet het. Gooit door — de aanroeper bepaalt wat een fout betekent. */
  async function haalEnCache(slug: string): Promise<AnnotatieDocument> {
    const document = await haalDocument(slug);
    setDocs((m) => ({ ...m, [slug]: document }));
    return document;
  }

  /** Achtergrond-variant voor de hydratatie: faalt stil, maar onthoudt wél een 404.
   *
   *  Zonder dat onderscheid is "verwijderd" niet van "de api ligt plat" te scheiden, en krijgt de
   *  jurist een *Opnieuw proberen* dat per definitie nooit kan slagen. Zo staat de kaart al als
   *  tombstone in beeld vóórdat er iemand op klikt.
   */
  async function laadDoc(slug: string): Promise<void> {
    try {
      await haalEnCache(slug);
    } catch (e) {
      if (isVerwijderd(e)) setVerwijderd((m) => ({ ...m, [slug]: true }));
    }
  }

  /** Deep-link `/workbench?annotatie=<slug>`: het artefact één keer openen bij binnenkomst.
   *  De ref voorkomt dat het paneel weer opengaat nadat de jurist het zelf heeft gesloten. */
  const deepLinkGeopend = useRef(false);
  useEffect(() => {
    if (!beginArtefact || deepLinkGeopend.current) return;
    deepLinkGeopend.current = true;
    void openArtefact(beginArtefact);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [beginArtefact]);

  async function openArtefact(slug: string) {
    setArtefactFout(null);
    // Al bekend als verwijderd: niet nog een keer proberen — er valt niets op te halen.
    if (verwijderd[slug]) {
      setArtefactWeg(slug);
      return;
    }
    setArtefactWeg(null);
    setArtefactLaadt(slug);
    try {
      const doc = docs[slug] ?? (await haalEnCache(slug));
      if (!infos[slug]) {
        const graaf = await haalArtikelGraaf(doc.bwbId, doc.artikel, doc.lid);
        setInfos((m) => ({ ...m, [slug]: graaf }));
      }
      setArtefactSlug(slug);
    } catch (e) {
      // Zichtbaar falen: de wettekst komt uit de graaf en die kan plat liggen. Een lege klik laat de
      // jurist denken dat de knop stuk is. Een verwijderd document is géén falen — dat wordt een
      // tombstone-kaart, geen foutbalk.
      if (isVerwijderd(e)) {
        setVerwijderd((m) => ({ ...m, [slug]: true }));
        setArtefactWeg(slug);
      } else setArtefactFout({ slug, melding: foutTekst(e) });
    } finally {
      setArtefactLaadt(null);
    }
  }

  /** Persisteer één beurt. Mislukken mag de chat niet blokkeren — maar ook niet stil gebeuren:
   *  de beurt staat dan wél in beeld en is na herladen weg. Eén onopvallende melding boven de thread
   *  is genoeg; per beurt een foutregel zou het gesprek onleesbaar maken. */
  async function persisteer(gid: string, rol: "user" | "assistant", velden: Record<string, unknown>) {
    try {
      await voegBerichtToe(gid, { rol, ...velden });
      setBewaarFout(null);
    } catch (e) {
      setBewaarFout(foutTekst(e));
    }
  }

  /** @param doel de bepaling, als die al vaststaat (zie `startRun`). */
  async function verstuur(vast?: string, doel?: AgentDoelInvoer) {
    const prompt = (vast ?? invoer).trim();
    if (!prompt || bezigRef.current) return;
    bezigRef.current = true;
    setInvoer("");

    // Een vraag bij een markering gaat als ADVIES: dezelfde thread, maar met contextblok en langs de
    // antwoordroute — die kan topologisch geen annotatie wijzigen.
    const context = vraagOver;
    setVraagOver(null);
    const contextLabel = context ? vraagContextLabel(context.el, docs[context.slug]) : "";
    // Vangnet: het paneel gaat al dicht zodra je "Vraag Lex" aanklikt, maar je kunt het intussen
    // opnieuw hebben geopend. Dan wint het antwoord — dat wil je zien binnenkomen.
    if (context && !breed) setArtefactSlug(undefined);

    // Toon de user-bubbel + antwoord-placeholder OPTIMISTISCH, vóór het (bij een nieuw gesprek) awaiten
    // van maakGesprek — anders "verdwijnt" het bericht tijdens die round-trip.
    const antId = uid();
    // Het id van de user-bubbel vasthouden: moet de beurt worden teruggedraaid (er liep er al een),
    // dan halen we precies déze weg. Filteren op de tekst zou een eerdere, identieke vraag treffen.
    const vraagId = uid();
    setItems((xs) => [
      ...xs,
      { id: vraagId, type: "user", tekst: prompt, over: contextLabel || undefined },
      { id: antId, type: "antwoord", tekst: "" },
    ]);
    setBezig(true);
    stickRef.current = true; // een nieuwe beurt springt altijd naar de bodem
    // Meldingen over de vórige beurt horen niet bij deze. `runVerdwenen` had geen enkele weg terug
    // behalve een herlaadbeurt, en bleef dus staan terwijl je alweer een vraag stelde.
    setRunVerdwenen(false);
    setVerbindingWeg(false);

    // Zorg voor een gesprek-id (maak er bij de eerste beurt één aan; titel = de vraag, afgekapt).
    let gid = gesprekId;
    if (!gid) {
      try {
        const g = await maakGesprek(prompt.slice(0, 80));
        gid = g.id;
        setGesprekId(gid);
        onGesprekAangemaakt(gid);
      } catch (e) {
        updateItem(antId, { tekst: `**Er ging iets mis.** ${foutTekst(e)}` });
        setBezig(false);
        bezigRef.current = false;
        return;
      }
    }

    // De chip is UI-state en reist niet mee naar de api; zonder deze regel leest een herladen gesprek
    // als een losse vraag zonder onderwerp.
    //
    // Bewust GEAWAIT: de vraag moet vastliggen vóórdat de run begint. De volgorde in de thread is de
    // autoincrement-id, dus een snelle beurt zou anders vóór zijn eigen vraag kunnen landen — en bij
    // het aanhaken na een herlaadbeurt is deze regel de user-bubbel waar het antwoord onder hoort.
    await persisteer(gid, "user", { tekst: contextLabel ? `Bij ${contextLabel}: ${prompt}` : prompt });

    // Markeringen die de jurist al maakte gaan mee: de Critic kan er dan een kanttekening bij
    // zetten. De agent kan niet zelf in het document kijken — dat leeft in de api. Alleen de
    // bepaling die nú open staat: de Critic beoordeelt ze tegen de tekst die hij zelf ophaalt, dus
    // markeringen uit een ander artikel kan hij daar per definitie niet in terugvinden.
    const reedsEigen = eigenMarkeringenVoorContext(artefactSlug ? docs[artefactSlug] : undefined);
    const basis = context
      ? {
          modus: "advies" as const,
          context: vraagContextVan(context.slug, docs[context.slug], infos[context.slug], context.el),
        }
      : reedsEigen.length
        ? { context: { bestaande_elementen: reedsEigen } }
        : undefined;
    // Een adviesvraag draagt nooit een doel: die route annoteert niet.
    const extra = doel && !context ? { ...basis, doel } : basis;

    let gestart;
    try {
      gestart = await startRun(prompt, gid, extra);
    } catch (e) {
      // Er liep al een beurt (bijvoorbeeld in een ander tabblad). Deze vraag is dus NIET aangenomen:
      // zet hem terug in het invoerveld en haal de optimistische bubbels weg, zodat er niets
      // stilzwijgend verdwijnt. Aanhaken bij de lopende beurt gebeurt hieronder.
      const lopend = (e as { loopendeRun?: string }).loopendeRun;
      if (lopend) {
        setItems((xs) => xs.filter((x) => x.id !== antId && x.id !== vraagId));
        setInvoer(prompt);
        setBewaarFout("Er liep al een vraag in dit gesprek; die wordt nu getoond. Je vraag staat weer in het invoerveld.");
        const hervatId = uid();
        setItems((xs) => [...xs, { id: hervatId, type: "antwoord", tekst: "" }]);
        await volgBeurt({ runId: lopend, gid, antId: hervatId, vanaf: 0 });
        return;
      }
      updateItem(antId, { tekst: `**Er ging iets mis.** ${foutTekst(e)}` });
      setBezig(false);
      bezigRef.current = false;
      return;
    }

    // Onthoud dát er een beurt liep. Komt de agent tussentijds opnieuw op, dan is dit het enige
    // spoor waarmee de werkplek kan zeggen wat er gebeurd is.
    schrijfLopendeRuns(onthoudRun(leesLopendeRuns(), gid, gestart.run_id));
    await volgBeurt({ runId: gestart.run_id, gid, antId });
  }

  /** Haak aan bij een run en verwerk hem tot het eind: verzamelen wat binnenkomt, en vastleggen wat
   *  eruit komt.
   *
   *  Eén functie voor twee ingangen — een verse beurt (`verstuur`) en het weer oppakken van een
   *  beurt die doorliep terwijl je ergens anders keek (`hervatBeurt`). Dat moet dezelfde code zijn,
   *  anders lopen de twee paden uit elkaar op precies het moment dat het ertoe doet.
   */
  async function volgBeurt({
    runId: id, gid, antId, vanaf = 0, herstel = 0,
  }: { runId: string; gid: string; antId: string; vanaf?: number; herstel?: number }) {
    // Het venster is tussen het besluit en dit moment verdwenen: niet alsnog aanhaken. De run zelf
    // loopt gewoon door bij de agent.
    if (!levendRef.current) return;
    const beheerser = new AbortController();
    afbrekenRef.current = beheerser;
    setRunId(id);
    bezigRef.current = true;
    setBezig(true);

    const doelRef: { d: AgentDoel | null } = { d: null };
    // Ontdubbeld verzamelen: de agent kan hetzelfde element in meerdere rondes opnieuw sturen
    // (annoteerder ⇄ Critic), en dan wint de laatste versie.
    let els: VoorstelElement[] = [];
    const ontbrekend: OntbrekendItem[] = [];
    const suggesties: { element_id: string; aandacht: string; motivatie: string }[] = [];
    let kandidaten: AgentKandidaat[] = [];
    // De herkomst van deze beurt (welk model), zodat de api kan vastleggen waar de voorstellen
    // vandaan komen. Blijft null bij een agent die het `run`-event nog niet stuurt.
    let run: AgentRun | null = null;
    let tekst = "";
    let denk = "";
    let bronnen: Bron[] = [];
    // Heeft de agent de beurt zelf vastgelegd? Dan schrijft de werkplek niets meer weg — anders
    // stond alles er twee keer. Blijft dit leeg, dan doet de client het zoals vroeger; zo werkt een
    // graph-qa zonder api-koppeling gewoon door.
    let opgeslagen: { annotatie_slug: string; run_id: string } | null = null;
    // De verbinding viel weg terwijl de run doorliep. Buiten de `try` gezet omdat het opnieuw
    // aanhaken ná de `finally` moet gebeuren: die reset `bezig`/`afbrekenRef`, en een nieuwe lus
    // die daarvóór begint raakt zijn eigen beheerser kwijt.
    let verbroken = false;
    // Kwam er iets over déze verbinding binnen? Zo ja, dan telt een volgende breuk als een verse
    // onderbreking en begint de wachttijd weer onderaan — anders zou een lange beurt met twee losse
    // dips in de hoogste backoff blijven hangen.
    let ontving = false;
    try {
      await volgRun(
        id,
        {
          onLeeft: () => {
            ontving = true;
            setVerbindingWeg(false);
            // Er ís weer contact met een lopende beurt; een eerdere "de agent is herstart"-melding
            // slaat nu nergens meer op.
            setRunVerdwenen(false);
          },
          onStatus: (m) => {
            denk += (denk ? "\n" : "") + "· " + m;
            updateItem(antId, { denk });
          },
          onReason: (t) => {
            denk += t;
            updateItem(antId, { denk });
          },
          onToken: (t) => {
            tekst += t;
            updateItem(antId, { tekst });
          },
          onSources: (b) => {
            bronnen = b;
            updateItem(antId, { bronnen: b });
          },
          onGrounding: (g) => updateItem(antId, { grounding: g }),
          onDoel: (d) => (doelRef.d = d),
          onElement: (e) => (els = mergeVoorstellen(els, e)),
          onRun: (r) => (run = r),
          onOntbrekend: (xs) => ontbrekend.push(...xs),
          onSuggestie: (s) => suggesties.push(s),
          onKandidaten: (k) => (kandidaten = k),
          // De eventlog van de run is gecapt: er is narratie weggevallen. Benoem dat, in plaats van
          // een tekst te tonen die compleet lijkt maar het niet is.
          // Er viel narratie weg doordat de eventlog gecapt is. Zet de markering in het spoor waar
          // hij hoort: stond er al antwoordtekst, dan is die mogelijk onvolledig; anders raakte het
          // alleen het denkproces en zou een "…" in het antwoord een gat suggereren dat er niet is.
          onGat: () => {
            if (tekst) {
              tekst += "\n\n…\n\n";
              updateItem(antId, { tekst });
            } else {
              denk += (denk ? "\n" : "") + "· (een deel van het spoor is niet bewaard)";
              updateItem(antId, { denk });
            }
          },
          onOpgeslagen: (uitkomst) => (opgeslagen = uitkomst),
          onWaarschuwing: (bericht) => setMelding(bericht),
        },
        vanaf,
        beheerser.signal,
      );
      // De stroom liep tot het einde: deze beurt is afgerond en het spoor mag weg. Bij loskoppelen
      // komen we hier niet (dat gooit een AbortError), en dan blijft het spoor terecht staan.
      vergeetLopendeRun(gid);

      // Kandidaten EERST: dit is een keuzelijst in de thread, geen uitkomst die is vastgelegd.
      // Stond deze tak onder de `opgeslagen`-check, dan sneed die hem af zodra graph-qa zelf ging
      // wegschrijven — en verdween de keuzelijst stilzwijgend uit beeld.
      if (kandidaten.length) {
        setItems((xs) =>
          xs.map((x) => (x.id === antId ? { id: antId, type: "kandidaten", tekst, kandidaten } : x)),
        );
        // Alleen de tekst overleeft een herlaadbeurt: de kandidaten zitten niet in het
        // berichtcontract van de api. Beter een leesbare opsomming dan "ik vond 5 bepalingen".
        // Heeft de agent de beurt al vastgelegd, dan schrijft de client niets meer — anders stond
        // de opsomming er twee keer.
        if (!opgeslagen) {
          void persisteer(gid, "assistant", { tekst: kandidatenAlsTekst(tekst, kandidaten), denk, run_id: id });
        }
        onGewijzigd();
        return;
      }

      // De agent heeft het vastgelegd. Nu alleen nog tonen wat er staat — de api is de bron.
      if (opgeslagen) {
        await toonVastgelegdeBeurt(opgeslagen, { antId, ontbrekend, denk });
        onGewijzigd();
        return;
      }

      const doel = doelRef.d;
      if (doel && doel.bwbId && els.length) {
        // De agent had dit moeten vastleggen (`agent/beurt.py`) en deed dat niet: geen
        // `opgeslagen`-event terwijl er wél markeringen waren. Dat is een storing en die tonen we
        // als storing.
        //
        // De werkplek schreef het hier vroeger zelf weg. Dat was een tweede, volledige
        // implementatie van dezelfde handeling — mét eigen artikelophaling en eigen titelopbouw —
        // en welke van de twee liep hing af van de aan/afwezigheid van één SSE-event. Bij een
        // gedeeltelijk falen leverde dat een tweede document op. Eén schrijver, en die is de agent.
        const melding =
          "**Deze beurt is niet vastgelegd.** De markeringen zijn wel voorgesteld, maar niet " +
          "opgeslagen. Stel de vraag opnieuw; blijft het gebeuren, meld het dan.";
        updateItem(antId, { tekst: melding, denk });
        void persisteer(gid, "assistant", { tekst: melding, denk, run_id: id });
      } else {
        if (!tekst.trim()) updateItem(antId, { tekst: "(geen antwoord)" });
        // `run_id` maakt dit bericht idempotent: kijken er twee tabbladen mee, dan landt de
        // uitkomst van deze run toch maar één keer.
        void persisteer(gid, "assistant", { tekst: tekst.trim() || "(geen antwoord)", denk, bronnen, run_id: id });
      }
      onGewijzigd();
    } catch (e) {
      // Losgekoppeld is géén fout en géén einde: de run draait door bij de agent en wordt opgepakt
      // zodra dit venster terugkomt. Niets bewaren dus — het definitieve antwoord komt later.
      // Een wegvallende verbinding is óók geen einde: de beurt is van de server. Zie
      // `naEenGebrokenStream` voor de regel en waarom hij bestaat.
      const besluit = naEenGebrokenStream(
        isAfgebroken(e), levendRef.current, definitieveStroomfout(e),
      );
      if (besluit === "negeren") {
        // Zelf losgekoppeld (stopknop, van gesprek wisselen): er valt niets meer te herstellen, dus
        // ook geen melding daarover laten staan.
        setVerbindingWeg(false);
        return;
      }
      verbroken = besluit === "opnieuw";
      // Bij een herkansing blijft de bubbel staan zoals hij is: het heraanhaken speelt de eventlog
      // opnieuw af, dus de tekst wordt zo meteen alsnog opgebouwd. Wat er aan de hand is staat in de
      // banner — die verdwijnt vanzelf zodra er weer iets binnenkomt.
      setVerbindingWeg(verbroken);
      if (!verbroken) updateItem(antId, { tekst: `**Er ging iets mis.** ${foutTekst(e)}` });
    } finally {
      afbrekenRef.current = null;
      setRunId(null);
      setStopt(false);
      setBezig(false);
      bezigRef.current = false;
    }

    if (verbroken && levendRef.current) {
      // Even wachten: valt de verbinding weg doordat de dienst opnieuw opstart, dan is meteen
      // opnieuw proberen gegarandeerd weer mis. De wachttijd loopt op, maar wordt gewekt zodra het
      // netwerk terug is of het tabblad weer in beeld komt. `vanaf: 0` speelt de hele eventlog
      // terug, dus wat er tijdens de onderbreking gebeurde komt alsnog in beeld — inclusief het
      // `opgeslagen`-event.
      const doorgaan = await wachtMetWekker(
        herstelWachttijd(herstel), () => levendRef.current,
      );
      if (!doorgaan) return;
      await volgBeurt({ runId: id, gid, antId, vanaf: 0, herstel: ontving ? 0 : herstel + 1 });
    }
  }

  /** De beurt is afgerond (of afgebroken); het spoor mag weg. */
  function vergeetLopendeRun(gid: string) {
    schrijfLopendeRuns(vergeetRun(leesLopendeRuns(), gid));
  }

  /** De agent heeft de beurt al weggeschreven; haal op wat er staat en toon het.
   *
   *  Bewust ophalen in plaats van de inhoud in het SSE-contract te proppen: dan blijft de api de ene
   *  bron van waarheid en groeit het eventcontract niet mee met het datamodel.
   */
  async function toonVastgelegdeBeurt(
    uitkomst: { annotatie_slug: string },
    { antId, ontbrekend, denk }: { antId: string; ontbrekend: OntbrekendItem[]; denk: string },
  ) {
    if (!uitkomst.annotatie_slug) return; // een gewoon antwoord staat al in beeld
    const doc = await laadDocEnGeef(uitkomst.annotatie_slug);
    if (!doc) {
      // De annotatie is wél vastgelegd, alleen niet op te halen. Toon de kaart tóch — met de slug
      // die we hebben — in plaats van een gewoon antwoord waar de jurist niets mee kan; anders is
      // het werk onvindbaar terwijl het gewoon in de api staat.
      setItems((xs) =>
        xs.map((x) =>
          x.id === antId
            ? { id: antId, type: "annotatie", slug: uitkomst.annotatie_slug, ontbrekend, denk }
            : x,
        ),
      );
      return;
    }
    if (!infos[doc.slug]) {
      const graaf = await haalArtikelGraaf(doc.bwbId, doc.artikel, doc.lid);
      setInfos((m) => ({ ...m, [doc.slug]: graaf }));
    }
    setItems((xs) =>
      xs.map((x) =>
        x.id === antId
          ? { id: antId, type: "annotatie", slug: doc.slug, titel: annotatieTitel(doc), ontbrekend, denk }
          : x,
      ),
    );
    setArtefactSlug(doc.slug);
  }

  /** Als `laadDoc`, maar geeft het document terug — `laadDoc` is de stille achtergrondvariant. */
  async function laadDocEnGeef(slug: string): Promise<AnnotatieDocument | null> {
    try {
      return await haalEnCache(slug);
    } catch (e) {
      if (isVerwijderd(e)) setVerwijderd((m) => ({ ...m, [slug]: true }));
      return null;
    }
  }

  /** Loopt er nog een beurt in dit gesprek? Haak er dan weer op aan.
   *
   *  Dit is de terugweg van de omkering: de run overleefde het wegklikken, dus bij binnenkomst
   *  hoort hij weer in beeld te komen — inclusief wat je gemist hebt (`vanaf: 0` speelt de eventlog
   *  af). Alleen bij een lópende run: een beurt die klaar is staat al in de gehydrateerde
   *  geschiedenis, en die twee keer tonen is erger dan hem missen.
   */
  async function hervatBeurt(gid: string, berichtRunIds: string[]) {
    if (bezigRef.current) return;
    const lopend = await haalActieveRun(gid);
    // Opnieuw toetsen ná de round-trip: typte de jurist ondertussen een vraag, dan draait die run al
    // en zouden hier twee lussen naast elkaar komen — met twee placeholders en een `afbrekenRef`
    // die de eerste kwijtraakt.
    if (bezigRef.current) return;
    // Niet kunnen vaststellen is geen "er liep niets": stil laten, anders meld je een afgebroken
    // beurt die in werkelijkheid gewoon doorloopt.
    if (lopend === "onbekend") return;
    if (lopend && lopend.status === "loopt") {
      const antId = uid();
      setItems((xs) => [...xs, { id: antId, type: "antwoord", tekst: "" }]);
      await volgBeurt({ runId: lopend.run_id, gid, antId, vanaf: 0 });
      return;
    }

    // Geen lopende run. Stond er wél een open? Dan is het register leeg — een herstart of deploy —
    // tenzij de beurt gewoon is afgerond en zijn bericht heeft achtergelaten.
    const stand = standVanVorigeRun(leesLopendeRuns()[gid], berichtRunIds);
    if (stand === "verdwenen") setRunVerdwenen(true);
    if (stand !== "geen") vergeetLopendeRun(gid);
  }

  /** Stop de lopende beurt. Een verzoek aan de agent, geen dichtvallende verbinding.
   *
   *  De agent-nodes zijn synchroon: een lopende LLM-call maakt zichzelf af en de run eindigt op de
   *  eerstvolgende grens. Dat kan tientallen seconden duren, dus de knop blijft in de "stopt"-stand
   *  staan tot het echt zover is — doen alsof het meteen klaar is zou liegen. Wat er tot dan toe
   *  binnenkwam, wordt gewoon vastgelegd zoals bij een normale afloop.
   */
  async function stop() {
    if (!runId || stopt) return;
    setStopt(true);
    try {
      await stopRun(runId);
    } catch {
      // Mislukt het stopverzoek, dan loopt de beurt gewoon door. Zet de knop terug in plaats van
      // hem eeuwig op "Stoppen…" te laten staan.
      setStopt(false);
    }
  }

  /** De jurist markeert zelf een fragment. Gooit door naar het paneel, dat de fout bij de selectie
   *  toont — daar staat de gebruiker met zijn aandacht, niet onderin de chatthread. */
  async function eigenMarkering(
    slug: string,
    invoer: { klasse: string; tekst: string; lid: string; toelichting: string; anker: Anker },
  ) {
    const oud = new Set((docs[slug]?.elementen ?? []).map((e) => e.id));
    const bij = await voegElementToe(slug, invoer);
    setDocs((m) => ({ ...m, [slug]: bij }));
    setMelding(`Gemarkeerd als ${invoer.klasse}.`);
    // Zet de verse markering meteen in beeld. De tekst toont alleen de geselecteerde, dus zonder dit
    // lijkt zelf markeren niets te doen: je selectie verdwijnt en er komt geen kleur voor terug.
    const nieuw = bij.elementen.find((e) => !oud.has(e.id));
    if (nieuw) setActiefId(nieuw.id);
  }

  /** Een eigen markering wissen. Alleen je eigen: een agent-voorstel verwérp je, zodat het
   *  auditspoor laat zien dát er een voorstel was. Was hij actief, dan valt de focus terug op de
   *  hele tekst — anders wijst `actiefId` naar een element dat niet meer bestaat. */
  async function wisEigenMarkering(slug: string, elementId: string) {
    await verwijderElement(slug, elementId);
    setDocs((m) => {
      const doc = m[slug];
      if (!doc) return m;
      return { ...m, [slug]: { ...doc, elementen: doc.elementen.filter((e) => e.id !== elementId) } };
    });
    setActiefId((huidig) => (huidig === elementId ? undefined : huidig));
    setMelding("Markering gewist.");
  }

  /** Afronden of heropenen. Gooit door naar het paneel, dat de fout bij de knop toont. */
  async function status(slug: string, nieuweStatus: "geaccordeerd" | "in_review") {
    const bij = await zetDocumentStatus(slug, nieuweStatus);
    setDocs((m) => ({ ...m, [slug]: bij }));
    setMelding(nieuweStatus === "geaccordeerd" ? "Annotatie afgerond." : "Annotatie heropend.");
  }

  async function beslissing(slug: string, elementId: string, req: BeslissingInvoer) {
    try {
      const bij = await beslis(slug, elementId, req);
      setDocs((m) => ({ ...m, [slug]: bij }));
      setMelding(beslissingMelding(req));
    } catch (e) {
      // Doorgooien: het artefact toont de fout bij de kaart waar hij ontstond. In de chatthread zou
      // hij het gesprek vervuilen met techniek, ver van de plek waar je aan het werk bent.
      throw e;
    }
  }

  function opToets(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // `isComposing`: met een IME (of een Android-toetsenbord dat een woordsuggestie met Enter
    // bevestigt) hoort Enter de compositie af te ronden, niet de beurt te versturen.
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void verstuur();
    }
  }

  // De laatste annotatie in dit gesprek: die hoort altijd één klik weg te zijn. Verwijderde
  // documenten slaan we over — anders verdwijnt de balk terwijl er verderop in het gesprek nog een
  // annotatie staat die wél bestaat.
  const laatsteAnnotatie = [...items]
    .reverse()
    .find((x): x is Extract<Item, { type: "annotatie" }> => x.type === "annotatie" && !verwijderd[x.slug])
    ?.slug;

  const artefact = artefactSlug && docs[artefactSlug] && infos[artefactSlug] && (
    <ArtefactPaneel
      variant={breed ? "kolom" : "side"}
      doc={docs[artefactSlug]}
      info={infos[artefactSlug]}
      ontbrekend={
        (items.find((x) => x.type === "annotatie" && x.slug === artefactSlug) as
          | { ontbrekend?: OntbrekendItem[] }
          | undefined)?.ontbrekend
      }
      actiefId={actiefId}
      // Nog eens op dezelfde markering klikken laat hem weer los. Selecteren zet de tekst in
      // focus (alleen die markering), dus zonder toggle zou je er niet meer uit komen.
      onKies={(id) => setActiefId((huidig) => (id && id === huidig ? undefined : id))}
      onBeslissing={(elementId, req) => beslissing(artefactSlug, elementId, req)}
      onEigenMarkering={(invoer) => eigenMarkering(artefactSlug, invoer)}
      onWisEigenMarkering={(elementId) => wisEigenMarkering(artefactSlug, elementId)}
      onStatus={(nieuweStatus) => status(artefactSlug, nieuweStatus)}
      onVraag={(el) => {
        setVraagOver({ slug: artefactSlug, el });
        // Op een smal scherm ligt het artefact óver de chat, dus stap hier al opzij — niet pas bij
        // het versturen. Anders lijkt "Vraag Lex" niets te doen: de chip met de markering en het
        // invoerveld staan achter het paneel, en je typt in een veld dat je niet ziet.
        if (!breed) setArtefactSlug(undefined);
        // Focus in dezelfde gebeurtenis als de klik: iOS opent het toetsenbord alleen binnen een
        // gebruikersgebaar.
        taRef.current?.focus();
      }}
      onSluit={() => setArtefactSlug(undefined)}
    />
  );

  return (
    <div className="flex min-h-0 min-w-0 flex-1">
    <div className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      {/* Beknopte statusmelding voor schermlezers (niet de hele thread live maken → geen token-spam). */}
      <p className="sr-only" aria-live="polite">
        {stopt ? "Bezig met stoppen; de agent rondt zijn huidige stap af." : bezig ? "Bezig met antwoorden…" : melding}
      </p>
      {/* De annotatie blijft bereikbaar. De chip in de thread scrolt weg zodra het gesprek doorloopt;
          dan is er geen weg terug naar het werk waar je middenin zat. */}
      {!artefactSlug && laatsteAnnotatie && docs[laatsteAnnotatie] && (
        <button
          type="button"
          onClick={() => void openArtefact(laatsteAnnotatie)}
          disabled={artefactLaadt === laatsteAnnotatie}
          className="focus-ring flex w-full shrink-0 items-center gap-2 border-b border-line bg-surface px-4 py-2 text-left text-xs text-muted transition hover:bg-surface-2 disabled:opacity-60"
        >
          <span className="truncate">
            <span className="font-medium text-ink">
              {docs[laatsteAnnotatie].werkgebied || docs[laatsteAnnotatie].bwbId} — art.{" "}
              {docs[laatsteAnnotatie].artikel}
            </span>{" "}
            · {docs[laatsteAnnotatie].elementen.length} elementen
            {teBeoordelen(docs[laatsteAnnotatie]) > 0 && ` · ${teBeoordelen(docs[laatsteAnnotatie])} te beoordelen`}
          </span>
          <span className="ml-auto shrink-0 font-medium text-lint">
            {artefactLaadt === laatsteAnnotatie ? "Openen…" : "Openen"}
          </span>
        </button>
      )}

      {artefactFout && (
        <div className="shrink-0 px-4 pt-2">
          <Melding type="fout" compact>
            De annotatie kon niet worden geopend ({artefactFout.melding}).{" "}
            <button
              type="button"
              onClick={() => void openArtefact(artefactFout.slug)}
              className="focus-ring rounded font-medium underline underline-offset-2"
            >
              Opnieuw proberen
            </button>
          </Melding>
        </div>
      )}

      {/* De verbinding met de lopende beurt is weg. Geen sluitknop: deze melding hóórt vanzelf te
          verdwijnen zodra de stroom weer loopt — dat is het hele punt. */}
      {verbindingWeg && (
        <div className="shrink-0 px-4 pt-2">
          <Melding type="waarschuwing" compact>
            De verbinding met Lex is weggevallen. Je vraag loopt gewoon door bij de agent; ik probeer
            opnieuw te verbinden…
          </Melding>
        </div>
      )}

      {/* Een herstart van de agent wist het run-register. Zeg dat, in plaats van een gesprek dat
          halverwege ophoudt zonder uitleg. */}
      {runVerdwenen && (
        <div className="shrink-0 px-4 pt-2">
          <Melding type="waarschuwing" compact>
            De vorige vraag is afgebroken doordat de agent opnieuw is opgestart. Stel hem gerust nog
            een keer.{" "}
            <button
              type="button"
              onClick={() => setRunVerdwenen(false)}
              className="focus-ring rounded font-medium underline underline-offset-2"
            >
              Sluiten
            </button>
          </Melding>
        </div>
      )}

      {/* Verwijderd is een toestand, geen storing: een neutrale mededeling zónder "Opnieuw proberen",
          want die knop kan hier per definitie niet slagen. */}
      {artefactWeg && (
        <div className="shrink-0 px-4 pt-2">
          <Melding type="uitleg" compact>
            Deze annotatie is verwijderd. Het gesprek blijft staan.{" "}
            <Link href="/annotaties" className="focus-ring rounded font-medium underline underline-offset-2">
              Alle annotaties
            </Link>
          </Melding>
        </div>
      )}

      {bewaarFout && (
        <div role="status" className="shrink-0 border-b border-fout/30 bg-fout/10 px-4 py-2 text-center text-[0.8125rem] text-fout">
          Dit gesprek wordt op dit moment niet bewaard ({bewaarFout}). Wat je hier ziet verdwijnt bij
          het herladen.
        </div>
      )}
      {/* Thread — enige scrollende gebied; berichten in een gecentreerde leeskolom */}
      <div ref={lijstRef} onScroll={onThreadScroll} className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-3xl space-y-6 px-4 py-8">
          {/* Lex stelt zich hier kort voor. Dit is de KORTE variant van het IDENTITEIT-blok in
              tools/graph-qa/agent/prompts.py — dezelfde kadering (hulpmiddel, de jurist beslist),
              minder woorden. De volledige tekst komt uit de agent zelf zodra iemand ernaar vraagt;
              verander je de een, verander dan de ander mee. Een afzenderloze "Waarmee kan ik
              helpen?" liet de gebruiker niet weten met wát hij te maken had. */}
          {items.length === 0 && (
            <div className="pt-[10dvh] text-center">
              <p className="font-display text-2xl font-semibold text-lint">Ik ben Lex</p>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                Het hulpmiddel voor wetsanalyse in deze werkplek: ik zoek bepalingen op in de
                kennisgraaf, citeer letterlijk en stel markeringen in JAS-klassen voor. Wat ik
                voorstel, beoordeel jij.
              </p>
              <p className="mx-auto mt-3 max-w-md text-sm text-faint">
                Stel een vraag over de wet- en regelgeving, of vraag een annotatie volgens het JAS.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-2">
                {VOORBEELDEN.map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => void verstuur(v)}
                    className="rounded-bubbel border border-line bg-paper px-4 py-2.5 text-left text-sm text-lint shadow-zacht transition-all hover:-translate-y-0.5 hover:border-lint/40 hover:shadow-kaart focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>
          )}

          {items.map((item, i) => {
            // Alleen de laatste beurt kan aan het streamen zijn; die krijgt platte tekst tot hij
            // klaar is (zie `StreamendeTekst`).
            const streamt = bezig && i === items.length - 1;
            return item.type === "user" ? (
              <div key={item.id} className="flex animate-rise flex-col items-end gap-1">
                {item.over && (
                  <span className="max-w-[85%] truncate rounded-full bg-surface px-2.5 py-0.5 text-[0.7rem] text-muted">
                    bij {item.over}
                  </span>
                )}
                <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-bubbel bg-lint/10 px-4 py-2.5 text-sm text-ink">
                  {item.tekst}
                </div>
              </div>
            ) : item.type === "antwoord" ? (
              <div key={item.id} className="group flex animate-rise gap-3">
                <LexAvatar />
                <div className="min-w-0 flex-1 text-sm text-ink">
                  <p className="mb-1 text-xs font-medium text-muted">Lex</p>
                  {item.denk && <DenkProces tekst={item.denk} actief={bezig && !item.tekst} />}
                  {item.tekst ? (
                    streamt ? (
                      <StreamendeTekst tekst={item.tekst} />
                    ) : (
                      // De afgekeurde citaten worden in de tekst zelf aangewezen; het blok eronder
                      // blijft staan voor wat níét in de weergave terug te vinden was.
                      <Markdown tekst={item.tekst} nietLetterlijk={item.grounding?.niet_letterlijk} />
                    )
                  ) : item.denk ? null : (
                    <Punten />
                  )}
                  {item.bronnen && item.bronnen.length > 0 && <Bronnen bronnen={item.bronnen} />}
                  {item.tekst && item.grounding && <Brongetrouwheid grounding={item.grounding} />}
                  {item.tekst && <KopieerKnop tekst={item.tekst} />}
                </div>
              </div>
            ) : item.type === "kandidaten" ? (
              <div key={item.id} className="group flex animate-rise gap-3">
                <LexAvatar />
                <div className="min-w-0 flex-1 text-sm text-ink">
                  <p className="mb-1 text-xs font-medium text-muted">Lex</p>
                  {item.tekst && <Markdown tekst={item.tekst} />}
                  <KandidatenKeuze
                    kandidaten={item.kandidaten}
                    bezig={bezig}
                    onKies={(k) => void verstuur(kandidaatPrompt(k), doelVanKandidaat(k))}
                  />
                </div>
              </div>
            ) : (
              <div key={item.id} className="animate-rise">
                {item.denk && <DenkProces tekst={item.denk} actief={false} label="Zo is dit tot stand gekomen" />}
                <AnnotatieChip
                  doc={docs[item.slug]}
                  titel={item.titel}
                  aantal={docs[item.slug]?.elementen.length}
                  verwijderd={!!verwijderd[item.slug]}
                  onOpen={() => void openArtefact(item.slug)}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* "Naar beneden"-pil: verschijnt als je weg van de bodem scrolt (bv. tijdens streamen). */}
      {toonNaarBeneden && (
        <button
          type="button"
          onClick={naarBeneden}
          aria-label="Naar nieuwste bericht"
          className="absolute bottom-24 left-1/2 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-line bg-paper text-lint shadow-kaart transition-colors hover:border-lint/40 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 5v14M19 12l-7 7-7-7" />
          </svg>
        </button>
      )}

      {/* Invoerbalk — gepind onderaan, gecentreerd, auto-groeiend */}
      <div className="shrink-0 bg-paper">
        <div className="mx-auto max-w-3xl px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
          {/* Waar de volgende vraag over gaat. Zichtbaar zolang hij geldt, want anders stel je
              ongemerkt een adviesvraag over een element dat je allang niet meer voor je hebt. */}
          {/* De vragen die bij een markering hoe dan ook gesteld worden, als één klik. Een leeg veld
              met "Wat wil je weten over deze markering?" is een open vraag op het moment dat je juist
              snel wilt beoordelen. Ze verdwijnen zodra er een beurt loopt: een tweede vraag zou de
              eerste toch afgewezen krijgen (er loopt al een run op dit gesprek). */}
          {vraagOver && !bezig && (
            <div className="mb-1.5 flex flex-wrap gap-1.5">
              {vraagSuggesties(vraagOver.el).map((vraag) => (
                <button
                  key={vraag}
                  type="button"
                  onClick={() => void verstuur(vraag)}
                  className="focus-ring inline-flex min-h-[24px] items-center rounded-full border border-line bg-paper px-2.5 py-1 text-xs text-muted transition hover:border-lint hover:text-ink coarse:min-h-[44px]"
                >
                  {vraag}
                </button>
              ))}
            </div>
          )}
          {vraagOver && (
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-lint/30 bg-lint/5 px-2.5 py-1 text-xs text-lint">
                <span className={`shrink-0 rounded px-1 text-[0.7rem] ${jasStyle(vraagOver.el.klasse)}`}>
                  {vraagOver.el.klasse}
                </span>
                <span className="truncate">“{vraagOver.el.tekst}”</span>
                <button
                  type="button"
                  onClick={() => setVraagOver(null)}
                  aria-label="Vraag niet aan dit element koppelen"
                  className="focus-ring shrink-0 rounded-full p-0.5 hover:bg-lint/10"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
                    <path d="M18 6 6 18M6 6l12 12" />
                  </svg>
                </button>
              </span>
            </div>
          )}
          <div className="flex items-end gap-2 rounded-bubbel border border-line bg-white px-2 py-1.5 shadow-zacht transition-shadow focus-within:border-lint focus-within:shadow-kaart">
            <textarea
              ref={taRef}
              value={invoer}
              onChange={(e) => setInvoer(e.target.value)}
              onKeyDown={opToets}
              rows={1}
              placeholder={vraagOver ? "Wat wil je weten over deze markering?" : "Stel een vraag of vraag een annotatie…"}
              className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
            />
            {/* Tijdens het antwoorden is dit de stopknop: hetzelfde plekje, andere betekenis — je hoeft
                niet te zoeken waar je moet klikken om te onderbreken. */}
            <button
              type="button"
              onClick={() => (bezig ? void stop() : void verstuur())}
              disabled={(!bezig && !invoer.trim()) || stopt}
              aria-label={bezig ? (stopt ? "Bezig met stoppen" : "Stoppen") : "Versturen"}
              title={stopt ? "De agent rondt zijn huidige stap nog af" : undefined}
              className="focus-ring mb-0.5 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-paper transition-colors hover:bg-accent-soft disabled:cursor-not-allowed disabled:opacity-40"
            >
              {stopt ? (
                // Stoppen kan tientallen seconden duren (de agent rondt zijn stap af). Een knop die
                // er hetzelfde uitziet maar niet meer reageert, leest als kapot; deze draait zolang
                // het wachten duurt.
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" className="motion-safe:animate-spin" aria-hidden>
                  <path d="M12 3a9 9 0 1 0 9 9" strokeLinecap="round" />
                </svg>
              ) : bezig ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden>
                  <rect x="5" y="5" width="14" height="14" rx="2" />
                </svg>
              ) : (
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M12 19V5M5 12l7-7 7 7" />
                </svg>
              )}
            </button>
          </div>
          <p className="mt-2 text-center text-xs text-faint">
            De agent bevraagt de kennisgraaf — controleer altijd de bron.
          </p>
        </div>
      </div>

      {/* Op een smal scherm schuift het artefact als overlay over de chat heen. */}
      {!breed && artefact}
    </div>

    {/* Op een breed scherm staat het ernaast: chat en review tegelijk in beeld. */}
    {breed && artefact && (
      <div className="hidden w-[min(34rem,42vw)] shrink-0 xl:block">{artefact}</div>
    )}
    </div>
  );
}

const VOORBEELDEN = [
  "Wat betekent het begrip 'belastingschuldige'?",
  "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
  "Welke artikelen gaan over invordering?",
];

/** Compacte kaart in de chatstroom die naar het annotatie-artefact leidt (opent het slide-in paneel). */
function AnnotatieChip({
  doc,
  titel,
  aantal,
  verwijderd = false,
  onOpen,
}: {
  doc?: AnnotatieDocument;
  /** Het label uit het bericht zelf (`annotatie_titel`); de terugval als `doc` er niet (meer) is. */
  titel?: string;
  aantal?: number;
  verwijderd?: boolean;
  onOpen: () => void;
}) {
  const label = doc
    ? `${doc.werkgebied || doc.bwbId} — art. ${doc.artikel}${doc.lid ? ` lid ${doc.lid}` : ""}`
    : titel || "Annotatie";

  // Een verwijderde annotatie is geen kapotte knop maar een grafsteen: het gesprek blijft leesbaar
  // (daarom de bewaarde titel), maar er valt niets meer te openen — dus ook geen knop die dat
  // suggereert. Wat er nog wél te doen valt is doorlopen naar het overzicht.
  if (verwijderd) {
    return (
      <div className="flex w-full items-center gap-3 rounded-kaart border border-dashed border-line bg-surface px-4 py-3 text-left">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-line/40 text-faint" aria-hidden>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          </svg>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium text-muted line-through decoration-faint">
            {label}
          </span>
          <span className="block text-xs text-muted">Deze annotatie is verwijderd</span>
        </span>
        <Link
          href="/annotaties"
          className="focus-ring inline-flex min-h-[24px] shrink-0 items-center rounded-full border border-line px-2.5 py-0.5 text-[11px] font-medium text-lint transition-colors hover:bg-surface-2 coarse:min-h-[44px]"
        >
          Alle annotaties
        </Link>
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex w-full items-center gap-3 rounded-kaart border border-line bg-surface px-4 py-3 text-left shadow-zacht transition-all hover:-translate-y-0.5 hover:border-lint/40 hover:shadow-kaart focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
    >
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-lint/10 text-lint" aria-hidden>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6M9 13l2 2 4-4" />
        </svg>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium text-ink">{label}</span>
        <span className="block text-xs text-muted">
          JAS-annotatie{typeof aantal === "number" ? ` · ${aantal} elementen` : ""} · review openen
        </span>
      </span>
      <span className="shrink-0 text-muted" aria-hidden>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="m9 18 6-6-6-6" />
        </svg>
      </span>
    </button>
  );
}

/** De keuzelijst bij een onderwerp-vraag: welke bepaling gaat de werkvoorraad in?
 *
 *  Eén klik = één annotatie-opdracht. Bewust géén multi-select met "annoteer alle vijf": elke
 *  annotatie is een eigen document met een eigen review, en vijf tegelijk starten maakt de
 *  reviewlast onzichtbaar op het moment dat je hem aangaat.
 */
function KandidatenKeuze({
  kandidaten,
  bezig,
  onKies,
}: {
  kandidaten: AgentKandidaat[];
  bezig: boolean;
  onKies: (k: AgentKandidaat) => void;
}) {
  return (
    <ul className="mt-2 flex flex-col gap-2">
      {kandidaten.map((k) => (
        <li key={`${k.bwbId}|${k.artikel}|${k.lid ?? ""}`}>
          <button
            type="button"
            disabled={bezig}
            onClick={() => onKies(k)}
            className="flex w-full items-center gap-3 rounded-kaart border border-line bg-surface px-4 py-3 text-left shadow-zacht transition-all hover:-translate-y-0.5 hover:border-lint/40 hover:shadow-kaart disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{kandidaatLabel(k)}</span>
              {k.fragment && <span className="mt-0.5 block line-clamp-2 text-xs text-muted">{k.fragment}</span>}
            </span>
            <span className="shrink-0 text-muted" aria-hidden>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="m9 18 6-6-6-6" />
              </svg>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function Punten() {
  return (
    <span className="inline-flex gap-1" aria-label="Bezig">
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
    </span>
  );
}

/** Klein avatar links van een antwoord van Lex (zelfde icoonstijl als de AnnotatieChip).
 *  Bewust een machine-icoon en geen monogram of gezicht: Lex heeft een naam om over te kunnen
 *  praten, niet om als collega te lezen — zijn voorstellen zijn voorstellen. */
function LexAvatar() {
  return (
    <span
      className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-lint/10 text-lint"
      aria-hidden
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 8V4H8" />
        <rect width="16" height="12" x="4" y="8" rx="2" />
        <path d="M2 14h2M20 14h2M15 13v2M9 13v2" />
      </svg>
    </span>
  );
}

/** Kopieert de letterlijke antwoordtekst; toont kort "Gekopieerd". Subtiel, hover-onthullend op desktop. */
function KopieerKnop({ tekst }: { tekst: string }) {
  const [gekopieerd, setGekopieerd] = useState(false);
  const [mislukt, setMislukt] = useState(false);
  // De "Gekopieerd"-melding weer weghalen, en de timer opruimen als het bericht ondertussen
  // verdwijnt (bv. bij het wisselen van gesprek).
  useEffect(() => {
    if (!gekopieerd) return;
    const id = window.setTimeout(() => setGekopieerd(false), 1500);
    return () => window.clearTimeout(id);
  }, [gekopieerd]);

  async function kopieer() {
    try {
      await navigator.clipboard.writeText(tekst);
      setGekopieerd(true);
      setMislukt(false);
    } catch {
      // Het klembord is niet overal beschikbaar (onbeveiligde origin, geweigerde toestemming). Een
      // klik waar niets van gebeurt leest als een kapotte knop — zeg dus dat het niet lukte.
      setMislukt(true);
    }
  }
  return (
    <button
      type="button"
      onClick={kopieer}
      aria-label="Antwoord kopiëren"
      className="mt-2 inline-flex items-center gap-1.5 rounded px-1.5 py-1 text-xs text-muted transition-opacity hover:text-lint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100 coarse:opacity-100"
    >
      {mislukt ? (
        <span className="text-fout">Kopiëren lukte niet</span>
      ) : gekopieerd ? (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M20 6 9 17l-5-5" />
          </svg>
          Gekopieerd
        </>
      ) : (
        <>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <rect width="14" height="14" x="8" y="8" rx="2" />
            <path d="M4 16V4a2 2 0 0 1 2-2h10" />
          </svg>
          Kopiëren
        </>
      )}
    </button>
  );
}

// Inklapbaar "Denkproces"-blok (Claude-stijl): streamt live terwijl de agent werkt (`actief`) en klapt
// automatisch dicht zodra het antwoord er is. De gebruiker kan het handmatig weer openen.
function DenkProces({
  tekst,
  actief,
  label = "Denkproces",
}: {
  tekst: string;
  actief: boolean;
  /** Bij een annotatie is dit geen "denkproces" maar het spoor van het samenspel tussen de agents. */
  label?: string;
}) {
  const [keuze, setKeuze] = useState<boolean | null>(null);
  const open = keuze ?? actief;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setKeuze(!open)}
        className="inline-flex items-center gap-1.5 rounded-full px-1 text-xs text-muted transition-colors hover:text-ink"
        aria-expanded={open}
      >
        {actief && <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent-soft" aria-hidden />}
        <span>{actief ? "Denkt na…" : label}</span>
        {/* De chevron wijst naar rechts (ingeklapt) en draait omlaag bij openen. */}
        <ChevronOmlaag className={`-rotate-90 transition-transform ${open ? "rotate-0" : ""}`} />
      </button>
      {open && (
        <div className="mt-1.5 whitespace-pre-wrap rounded-kaart border border-line bg-surface px-3 py-2 text-xs leading-relaxed text-muted [overflow-wrap:anywhere]">
          {tekst}
        </div>
      )}
    </div>
  );
}

// Inklapbare bronnenlijst — standaard dicht met een teller, want de lijst kan lang zijn.
/** Wat de brongetrouwheidstoets van dit antwoord vond — alleen als er iets te melden is.
 *
 *  Bij een schoon resultaat zwijgt dit blok: de bronnenlijst eronder is dan het signaal, en een
 *  groen vinkje bij elk antwoord leert mensen er overheen te kijken. De twee gevallen die er wél
 *  toe doen:
 *
 *  - **onbepaald** — het antwoord noemde geen vindplaats en geen citaat, dus er viel niets te
 *    controleren. Dat is nadrukkelijk niet hetzelfde als "gecontroleerd en juist"; die twee vielen
 *    voorheen samen in één bool, en de UI liet ze allebei weg.
 *  - **ongegrond** — er staat een verwijzing in die niet uit de graaf kwam, of een citaat dat niet
 *    letterlijk in de opgehaalde tekst staat. Dat is precies waar een jurist op afgaat. */
function Brongetrouwheid({ grounding }: { grounding: AgentGrounding }) {
  if (grounding.niveau === "gegrond") return null;
  const onbepaald = grounding.niveau === "onbepaald";
  return (
    <div
      className={`mt-2 flex items-start gap-2 rounded-kaart border px-3 py-2 text-xs ${
        onbepaald
          ? "border-line bg-surface text-muted"
          : "border-aandacht-geel-rand bg-aandacht-geel-bg text-aandacht-geel-tekst"
      }`}
    >
      <span className="mt-0.5">{onbepaald ? <Cirkel /> : <Waarschuwing />}</span>
      <span className="min-w-0">
        {onbepaald ? (
          "Dit antwoord noemt geen vindplaats of letterlijk citaat, dus er valt niets te controleren tegen de graaf."
        ) : (
          <>
            {grounding.unsupported.length > 0 && (
              <span className="block break-words">
                Niet uit de graaf: {grounding.unsupported.join(", ")}
              </span>
            )}
            {grounding.niet_letterlijk.length > 0 && (
              <span className="block break-words">
                {grounding.niet_letterlijk.length === 1 ? "Dit citaat staat" : "Deze citaten staan"} niet
                letterlijk in de opgehaalde tekst: {grounding.niet_letterlijk.map((c) => `“${c}”`).join(" · ")}
              </span>
            )}
          </>
        )}
      </span>
    </div>
  );
}

function Bronnen({ bronnen }: { bronnen: Bron[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink"
        aria-expanded={open}
      >
        <span className="font-medium">Bronnen ({bronnen.length})</span>
        {/* De chevron wijst naar rechts (ingeklapt) en draait omlaag bij openen. */}
        <ChevronOmlaag className={`-rotate-90 transition-transform ${open ? "rotate-0" : ""}`} />
      </button>
      {open && (
        <div className="mt-1.5 break-words rounded-kaart border border-line bg-surface px-3 py-2 text-xs text-muted [overflow-wrap:anywhere]">
          {bronnen.map((b, i) => {
            const href = bronHref(b.uri);
            return (
              <span key={i}>
                {i > 0 && ", "}
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-lint underline underline-offset-2 [overflow-wrap:anywhere]"
                  >
                    {b.label}
                  </a>
                ) : (
                  b.label
                )}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
