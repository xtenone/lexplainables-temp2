import { isApiError } from "./api";
import { naamVan, vindplaatsLabel } from "./annotatieOverzicht";
import { jasVolgorde } from "./jas";
import type { LidRegel } from "./selectie";
import type {
  AgentContext,
  AgentDoelInvoer,
  AgentKandidaat,
  AnnotatieDocument,
  AnnotatieElement,
  GraafArtikel,
  DocumentStatus,
  ReviewReason,
  VoorstelElement,
  Wijziging,
} from "./types";

// Presentatie-helpers voor de annotatie-workbench (statuslabels/kleuren).

export const DOCUMENT_STATUS_LABEL: Record<DocumentStatus, string> = {
  in_review: "In behandeling",
  geaccordeerd: "Geaccordeerd",
  gepromoveerd: "In de graaf",
};

// Badge-tone per status (via de design-tokens, geen losse hex): in behandeling = aandacht-oker,
// geaccordeerd = aandacht-groen, in de graaf = lintblauw.
export const DOCUMENT_STATUS_STYLE: Record<DocumentStatus, string> = {
  in_review: "bg-aandacht-geel-bg text-aandacht-geel-tekst border-aandacht-geel-rand",
  geaccordeerd: "bg-aandacht-groen-bg text-aandacht-groen-tekst border-aandacht-groen-rand",
  gepromoveerd: "bg-lint/10 text-lint border-lint/25",
};

export function documentStatusLabel(status: DocumentStatus): string {
  return DOCUMENT_STATUS_LABEL[status] ?? status;
}

// --- de brontekst van een bepaling ------------------------------------------------------------------

/** De artikeltekst als regels: wat er op het scherm komt, mét het lidnummer dat erbij hoort.
 *
 *  Eén plek waar de weergave wordt opgebouwd, zodat het documentpaneel, de sortering, de ankers en de
 *  lid-toewijzing over dezelfde tekst praten. Het lidnummer reist apart mee omdat het niet uit de
 *  volgorde is af te leiden (zie `lidUitOffset`). Lege leden vallen weg — die zouden een lege regel in
 *  de bron zetten en alle offsets erna verschuiven. */
export function regelsVan(info: GraafArtikel): LidRegel[] {
  return info.leden_teksten
    .filter((l) => l.tekst.trim())
    .map((l) => ({ lid: l.lid ?? "", regel: l.lid ? `${l.lid}. ${l.tekst}` : l.tekst }));
}

/** De regels als één brontekst. Twee nieuwe regels ertussen — dezelfde scheiding waar `lidUitOffset`
 *  en de ankers van uitgaan. */
export function bronVan(regels: LidRegel[]): string {
  return regels.map((r) => r.regel).join("\n\n");
}

/** Voeg een binnenkomend `element`-event samen met wat er al verzameld is.
 *
 *  De agent kan hetzelfde element in meerdere rondes opnieuw sturen (annoteerder ⇄ Critic). Zonder
 *  ontdubbelen zou de werkplek dan duplicaten tonen én naar de server sturen. Matcht op `id`, met
 *  dezelfde terugval als de server (genormaliseerde tekst + lid) voor voorstellen zonder id.
 *  De laatste versie wint: die is door de meest recente Critic-ronde gegaan.
 *
 *  De **klasse telt niet mee** in de terugval — een herziening mag juist herclassificeren en moet
 *  dan hetzelfde element treffen. Canonieke regel: `routers/annotatie.py:_sleutel` (api) en
 *  `agent/annotatie.py:sleutel_van` (graph-qa), met dezelfde tabel in beider tests.
 *
 *  Eén bewuste afwijking van de server: staat er al een element mét id en komt hetzelfde fragment
 *  zónder id binnen, dan houdt de werkplek ze apart terwijl de api ze zou samenvoegen. De agent
 *  geeft elk voorstel een id, dus dat geval komt in de stroom niet voor; het id leidend houden is
 *  hier veiliger dan raden.
 */
export function mergeVoorstellen(
  bestaand: VoorstelElement[],
  binnen: VoorstelElement,
): VoorstelElement[] {
  const sleutel = (e: VoorstelElement) =>
    e.id ? `id:${e.id}` : `t:${e.tekst.split(/\s+/).join(" ").toLowerCase()}|${e.lid ?? ""}`;
  const doel = sleutel(binnen);
  const index = bestaand.findIndex((e) => sleutel(e) === doel);
  if (index < 0) return [...bestaand, binnen];
  const kopie = [...bestaand];
  kopie[index] = binnen;
  return kopie;
}

/** Mensleesbare aanduiding van een kandidaat-bepaling ("Artikel 36a, lid 1 — Invorderingswet 1990"). */
export function kandidaatLabel(k: AgentKandidaat): string {
  const bepaling = `Artikel ${k.artikel}${k.lid ? `, lid ${k.lid}` : ""}`;
  return k.citeertitel ? `${bepaling} — ${k.citeertitel}` : bepaling;
}

/** De gekozen kandidaat als **doel**: hiermee hoeft de agent niets meer te zoeken.
 *
 *  Dit is de belangrijkste plek voor een meegegeven doel. De jurist wees zojuist één bepaling aan
 *  uit een lijst; die opnieuw in natuurlijke taal laten opzoeken is niet alleen verspilling, het is
 *  de enige stap waar de keten alsnog bij een ándere bepaling kan uitkomen.
 */
export function doelVanKandidaat(k: AgentKandidaat): AgentDoelInvoer {
  return {
    bwbId: k.bwbId,
    artikel: k.artikel,
    ...(k.lid ? { lid: k.lid } : {}),
    ...(k.citeertitel ? { citeertitel: k.citeertitel } : {}),
  };
}

/** De opdracht die volgt als de jurist een kandidaat kiest.
 *
 *  Blijft naast `doelVanKandidaat` bestaan: dit is de **leesbare** vraag in de thread, en die hoort
 *  te zeggen wat er gebeurt. Het bwbId gaat er nog steeds in mee — draait er ooit een beurt zonder
 *  doel (een oudere client, of een agent die het veld negeert), dan is de tekst nog steeds
 *  eenduidig genoeg om bij de juiste bepaling uit te komen.
 */
export function kandidaatPrompt(k: AgentKandidaat): string {
  const bepaling = `artikel ${k.artikel}${k.lid ? ` lid ${k.lid}` : ""}`;
  const regeling = k.citeertitel ? `${k.citeertitel} (${k.bwbId})` : k.bwbId;
  return `Annoteer ${bepaling} van de ${regeling}.`;
}

/** De keuze als tekst, zodat de thread na herladen nog laat zien wát er te kiezen viel.
 *
 *  De kandidaten zelf zijn geen onderdeel van het berichtcontract van de api; alleen deze tekst
 *  wordt bewaard. Zonder dit leest een herladen gesprek als "Ik vond 5 bepalingen" zonder welke.
 */
export function kandidatenAlsTekst(melding: string, kandidaten: AgentKandidaat[]): string {
  const regels = kandidaten.map((k) => `- ${kandidaatLabel(k)}`);
  return [melding.trim(), ...regels].filter(Boolean).join("\n");
}

// `gewijzigdeVelden` en `redenVoorWijziging` stonden hier: de browser leidde de `review_reason` af
// uit wát er veranderde. Die afleiding is naar de api verhuisd (`routers/annotatie.py:
// _reden_uit_diff`), want daar wordt de diff toch al berekend. De reden in het auditspoor was
// anders een waarde die de server aannam maar nooit kon toetsen — te zwak voor een systeem dat om
// herleidbaarheid draait. De ervaring blijft gelijk: de jurist krijgt nog steeds geen dropdown.

/** Raakt een selectie het bereik van de actieve markering?
 *
 *  Zo ja, dan pas je die markering aan in plaats van een tweede te maken. Aanraken op de rand telt
 *  mee (`eind === start`): uitbreiden begint per definitie waar de markering ophoudt.
 */
export function overlaptSelectie(
  selectie: { start: number; eind: number },
  bereik: { start: number; eind: number },
): boolean {
  return selectie.start <= bereik.eind && selectie.eind >= bereik.start;
}

// --- de reviewlijst ordenen -----------------------------------------------------------------------

/** Elementen waar de jurist al over besloten heeft. Ook `edited`: een aanpassing ís een besluit. */
export const BESLIST_LIFECYCLES = ["human_approved", "edited", "rejected"];

export type ReviewFilter = "alles" | "te_beoordelen" | "aandacht";

export function isBeslist(el: AnnotatieElement): boolean {
  return BESLIST_LIFECYCLES.includes(el.lifecycle);
}

/** Staat dit ontbrekend-item inmiddels als markering in het document?
 *
 *  Matcht op klasse + genormaliseerd fragment. **Verworpen elementen tellen niet mee**: die heb je
 *  net weggestuurd, dus "inmiddels gemarkeerd" is dan precies het omgekeerde van wat er gebeurde —
 *  en het item bleef onaanklikbaar staan terwijl je hem juist opnieuw wilde kunnen toevoegen.
 *  Dezelfde regel als in `DocumentPaneel`, dat verworpen markeringen ook niet meer oplicht. */
export function alGemarkeerd(elementen: AnnotatieElement[], klasse: string, fragment: string): boolean {
  const sleutel = (k: string, t: string) => `${k}|${t.split(/\s+/).join(" ").toLowerCase()}`;
  const tekst = fragment.trim();
  if (!tekst) return false;
  return elementen.some(
    (e) => e.lifecycle !== "rejected" && sleutel(e.klasse, e.tekst) === sleutel(klasse, tekst),
  );
}

/** Lifecycles waarin het element een eindoordeel draagt en dus op slot zit — wijzigen kan pas na een
 *  expliciete heropening (`type: "heropen"`). Bewust NIET hetzelfde begrip als `isBeslist`, dat de
 *  filters en de telling stuurt: `edited` telt wel als beslist maar blijft bewerkbaar, want een
 *  klasse wijzigen en er daarna een toelichting bij typen is één doorlopende handeling. */
export const VERGRENDELDE_LIFECYCLES = ["human_approved", "rejected"];

export function isVergrendeld(el: AnnotatieElement): boolean {
  // Je eigen markering staat meteen op `human_approved` — je hoeft hem niet nog eens goed te keuren.
  // Dat is "gemaakt", niet "beoordeeld": vergrendelen zou hem bij het aanmaken al op slot zetten,
  // inclusief de wisknop. Wat je zelf maakte wis je (met een bevestiging); het slot beschermt een
  // review-oordeel over een voorstel van Lex.
  if (el.herkomst === "mens") return false;
  return VERGRENDELDE_LIFECYCLES.includes(el.lifecycle);
}

/** Een afgerond document is in zijn geheel bevroren — ook voor een nieuwe agent-ronde. De api
 *  weigert elke mutatie met een 409; de UI laat het slot zien in plaats van die fout af te wachten. */
export function isDocumentVergrendeld(doc: { status: DocumentStatus }): boolean {
  return doc.status === "geaccordeerd";
}

/** Hoort dit element bij de gekozen filterstand? */
export function pastInFilter(el: AnnotatieElement, filter: ReviewFilter): boolean {
  if (filter === "te_beoordelen") return !isBeslist(el);
  if (filter === "aandacht") return el.aandacht === "rood" || el.aandacht === "geel";
  return true;
}

/** Lidnummer als getal, voor sorteren. Lexicaal zou "10" vóór "2" zetten; een leeg lid komt eerst. */
function lidRang(lid: string): number {
  const n = Number.parseInt(lid, 10);
  return Number.isNaN(n) ? -1 : n;
}

/** Sorteer de reviewlijst in één vaste, inhoudelijke volgorde: de canonieke JAS-tabel.
 *
 *  Eerder woog aandacht (🔴🟡🟢) en voortgang het zwaarst. Beide veranderen terwijl je reviewt: keur
 *  je iets goed, dan sprong het naar achteren en schoof de rest op — je raakte je plek kwijt en een
 *  kaart stond nooit twee keer op dezelfde hoogte. Scherpstellen op twijfelgevallen doen de filters.
 *
 *  Sleutels van grof naar fijn: klasse (wa-tabelvolgorde) → lid → positie in de tekst →
 *  invoervolgorde. Geen van die vier verandert door reviewen; alleen als jíj de klasse wijzigt
 *  verhuist een element, en dan hóórt het ergens anders.
 *
 *  `posities` is de offset per element-id in de brontekst (het artefact berekent die met dezelfde
 *  `vindPositie` als de weergave). Ontbreekt hij, dan sorteert deze functie een niveau grover in
 *  plaats van te struikelen; een element dat niet in de tekst te vinden is komt achteraan binnen
 *  zijn eigen klasse.
 */
export function sorteerReview(
  elementen: AnnotatieElement[],
  posities?: Map<string, number>,
): AnnotatieElement[] {
  const positie = (el: AnnotatieElement) => posities?.get(el.id) ?? Number.POSITIVE_INFINITY;
  return elementen
    .map((el, i) => ({ el, i }))
    .sort((a, b) => {
      const klasse = jasVolgorde(a.el.klasse) - jasVolgorde(b.el.klasse);
      if (klasse !== 0) return klasse;
      const lid = lidRang(a.el.lid) - lidRang(b.el.lid);
      if (lid !== 0) return lid;
      // Let op: niet `pa - pb` — met twee keer Infinity levert dat NaN, en met één Infinity een
      // waarde die de "niet gevonden"-kaart niet betrouwbaar achteraan zet.
      const pa = positie(a.el);
      const pb = positie(b.el);
      if (pa !== pb) return pa === Number.POSITIVE_INFINITY ? 1 : pb === Number.POSITIVE_INFINITY ? -1 : pa - pb;
      return a.i - b.i;
    })
    .map(({ el }) => el);
}

/** Het volgende (of vorige) element in de getoonde volgorde.
 *
 *  `alleenTeBeoordelen` is het auto-advance-gedrag na een akkoord: doorspringen naar het volgende dat
 *  nog aandacht vraagt in plaats van naar het eerstvolgende in de lijst. Geeft `undefined` als er
 *  niets meer is — dan blijft de selectie staan in plaats van naar het begin te springen.
 */
export function volgendeElement(
  lijst: AnnotatieElement[],
  actiefId: string | undefined,
  richting: 1 | -1 = 1,
  alleenTeBeoordelen = false,
): AnnotatieElement | undefined {
  const kandidaten = alleenTeBeoordelen ? lijst.filter((el) => !isBeslist(el)) : lijst;
  if (kandidaten.length === 0) return undefined;

  const huidig = kandidaten.findIndex((el) => el.id === actiefId);
  if (huidig < 0) {
    // Niets geselecteerd (of het actieve element valt buiten de kandidaten): begin bij de rand.
    return richting === 1 ? kandidaten[0] : kandidaten[kandidaten.length - 1];
  }
  return kandidaten[huidig + richting];
}

// --- een vraag over één markering ------------------------------------------------------------------

/** Hoeveel andere markeringen er hoogstens meegaan. Een bepaling kan er tientallen hebben; dan is de
 *  lijst geen hulp meer maar promptvulling. */
const MAX_BUREN = 20;

/** Bouw het contextblok voor een adviesvraag bij een element.
 *
 *  De agent kan niet in het document kijken; deze context vertelt hem waar de vraag over gaat. `lid`
 *  valt terug op het document als het element zelf er geen heeft (bij een artikel zonder leden), en
 *  het corpus is de getoonde artikeltekst — dezelfde die de jurist voor zich ziet.
 */
export function vraagContextVan(
  slug: string,
  doc: AnnotatieDocument | undefined,
  info: GraafArtikel | undefined,
  el: AnnotatieElement,
): AgentContext {
  return {
    slug,
    bwbId: doc?.bwbId,
    artikel: doc?.artikel,
    lid: el.lid || doc?.lid,
    element_id: el.id,
    klasse: el.klasse,
    fragment: el.tekst,
    corpus: info?.leden_teksten.map((l) => l.tekst).join("\n\n"),
    // De overige markeringen gaan mee, zodat de agent er bij de onderbouwing naar kan verwijzen
    // (samenhang, afbakening) zonder ervoor terug te vallen op het gespreksgeheugen. Zou hij dat wel
    // doen, dan verschilt het antwoord op dezelfde vraag per gesprek. Verworpen elementen blijven
    // eruit — die zijn juist afgekeurd — en het gevraagde element ook: dat staat al als `fragment`.
    bestaande_elementen: (doc?.elementen ?? [])
      .filter((e) => e.id !== el.id && e.lifecycle !== "rejected")
      .slice(0, MAX_BUREN)
      .map((e) => ({ id: e.id, klasse: e.klasse, tekst: e.tekst, lid: e.lid, herkomst: e.herkomst })),
  };
}


/** De eigen markeringen die als context meegaan met een ANNOTATIE-beurt.
 *
 *  De Critic kijkt ermee mee op eigen werk. Dat kan alleen zinnig over de bepaling die hij voor zich
 *  heeft, dus gaat hier één document in — niet alles wat er in het gesprek is geopend. Dat laatste
 *  deed de werkplek eerder wél (`Object.values(docs).flatMap(...)`), waardoor een markering bij
 *  artikel 36 werd beoordeeld tegen de tekst van artikel 8.
 *
 *  Verworpen markeringen blijven eruit en de lijst is begrensd, net als bij `vraagContextVan`.
 */
export function eigenMarkeringenVoorContext(
  doc: AnnotatieDocument | undefined,
): NonNullable<AgentContext["bestaande_elementen"]> {
  return (doc?.elementen ?? [])
    .filter((e) => e.herkomst === "mens" && e.lifecycle !== "rejected")
    .slice(0, MAX_BUREN)
    .map((e) => ({ id: e.id, klasse: e.klasse, tekst: e.tekst, lid: e.lid, herkomst: e.herkomst }));
}

/** Korte aanduiding van waar een vraag over gaat, voor de chip én voor het bewaarde bericht.
 *
 *  Zonder deze regel leest een herladen gesprek als een losse vraag zonder onderwerp: de chip is
 *  UI-state en gaat niet mee naar de api.
 */
export function vraagContextLabel(el: AnnotatieElement, doc?: AnnotatieDocument): string {
  const plek = doc ? ` (art. ${doc.artikel}${el.lid ? ` lid ${el.lid}` : ""})` : "";
  return `${el.klasse} — “${el.tekst}”${plek}`;
}

/** Drie vragen die bij het beoordelen van een markering het vaakst gesteld worden.
 *
 *  Een leeg invoerveld met "Wat wil je weten over deze markering?" is een open vraag op het moment
 *  dat je juist snel wilt beoordelen. Deze drie zijn de vragen die een jurist bij een JAS-markering
 *  hoe dan ook stelt: klopt de klasse, klopt de afbakening, en — als er twijfel is — waarom die
 *  andere klasse dan niet.
 *
 *  De derde past zich aan, want daar zit het verschil per element. Bij een gedisambigueerd voorstel
 *  is "waarom geen Voorwaarde?" een scherpere vraag dan welke vaste formulering ook; zonder
 *  alternatieven is de samenhang met de rest van het artikel het eerstvolgende dat je wilt weten.
 */
export function vraagSuggesties(el: AnnotatieElement): string[] {
  const anders = el.alternatieven[0]?.klasse;
  return [
    `Waarom is dit een ${el.klasse}?`,
    "Klopt de afbakening van dit fragment?",
    anders
      ? `Waarom geen ${anders}?`
      : "Hoe verhoudt dit zich tot de rest van het artikel?",
  ];
}

// --- een annotatie die er niet meer is ---------------------------------------------------------

/** Het leesbare label van een annotatie: "Invorderingswet 1990 — art. 9 lid 1".
 *
 *  Eén samenstelling voor de kop van de annotatiepagina én voor het label dat met de chatbeurt wordt
 *  meebewaard (`annotatie_titel`). Dat meebewaren is de kern: een bericht verwijst met een kale slug
 *  naar een document zonder foreign key, dus zodra dat document verwijderd is valt er niets meer op
 *  te halen — en dan moet de kaart in de thread zichzelf nog kunnen benoemen.
 */
export function annotatieTitel(doc: {
  citeertitel?: string;
  werkgebied?: string;
  bwbId: string;
  artikel: string;
  lid: string;
}): string {
  return `${naamVan(doc)} — ${vindplaatsLabel(doc)}`;
}

/** Is deze fout "bestaat niet (meer)" in plaats van "het ging even mis"?
 *
 *  De api geeft 404 zowel bij een verwijderd document als bij dat van iemand anders (bewust: dat lekt
 *  het bestaan niet). Beide betekenen voor de UI hetzelfde: opnieuw proberen kan per definitie niet
 *  lukken, dus toon een toestand en geen foutmelding met een retry-knop.
 */
export function isVerwijderd(e: unknown): boolean {
  return isApiError(e) && e.status === 404;
}
