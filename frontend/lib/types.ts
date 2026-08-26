// Domeintypes — handmatig afgeleid van het API-contract (api/app/*.py).
// Dit bestand is de bron-van-waarheid voor de frontend; zie README (gen:types) voor
// een optioneel hulpmiddel om ze tegen /openapi.json te controleren.

// --- Catalogus (niet-admin): keuzelijsten -----------------------------------

export interface ProfileChoice {
  name: string;
  is_default: boolean;
}

// --- Admin: LLM-modelprofielen ----------------------------------------------

export interface LlmProfileIn {
  provider?: string;
  model?: string;
  api_base?: string;
  api_version?: string | null;
  output_strategy?: string;
  temperature?: number;
  /** Write-only: leeg laten = bestaande key ongewijzigd. */
  api_key?: string;
  is_default?: boolean;
}

export interface LlmProfileOut {
  name: string;
  provider: string;
  model: string;
  api_base: string;
  api_version: string | null;
  output_strategy: string;
  temperature: number;
  is_default: boolean;
  api_key_set: boolean;
  updated_by: string;
  updated: string;
}

export interface TestResult {
  ok: boolean;
  model: string;
  tokens_in: number;
  tokens_out: number;
  detail: string;
}

// --- Auth: accounts + rollen ------------------------------------------------

export type Role = "beheerder" | "analist";

export interface UserOut {
  userid: string;
  email: string;
  role: Role;
  totp_enabled: boolean;
  active: boolean;
  created: string;
  updated: string;
}

/** Antwoord bij aanmaken/resetten: het tijdelijke wachtwoord wordt eenmalig getoond. */
export interface UserCreated extends UserOut {
  temp_password: string;
}

export interface TempPassword {
  userid: string;
  temp_password: string;
}

// --- Genereerbare API-tokens (admin) ------------------------------------------

export interface ApiTokenOut {
  id: string;
  label: string;
  token_prefix: string;
  scope: string;
  active: boolean;
  created_by: string;
  created: string;
  last_used: string | null;
}

/** Antwoord bij genereren: het volledige token wordt eenmalig getoond en nergens bewaard. */
export interface ApiTokenCreated extends ApiTokenOut {
  token: string;
}

/** Eigen account (self-service); spiegelt /v1/auth/me. */
export interface MeAccount {
  userid: string;
  email: string;
  role: Role;
  totp_enabled: boolean;
}

export interface TotpBegin {
  otpauth_uri: string;
}

/** Uitkomst van de login-pre-check (/api/login-verify). code: "" | "ok" | "invalid" | "totp_required" | "rate". */
export interface LoginVerifyResult {
  ok: boolean;
  code: string;
  userid: string;
  email: string;
  role: Role | "";
}

// --- API-fout doorgegeven door de BFF ---------------------------------------

export interface ApiError {
  status: number;
  detail: string;
  retryAfter?: number;
}

// --- Annotatie-domein (wetsanalyse-workbench) — afgeleid van api/app/annotatie_contracts.py ---

export type Lifecycle =
  | "voorgesteld" | "critic_checked" | "human_approved" | "edited" | "rejected" | "published" | "reused";
export type BeslissingType = "approve" | "edit" | "reject" | "comment" | "heropen";
export type ReviewReason =
  | "verkeerde_klasse" | "bron_gemist" | "tekst" | "interpretatie" | "onvoldoende_context" | "anders";
export type Aandacht = "groen" | "geel" | "rood";
export type DocumentStatus = "in_review" | "geaccordeerd" | "gepromoveerd";

export interface Alternatief {
  klasse: string;
  motivatie: string;
}

export interface Beslissing {
  type: BeslissingType;
  actor: string;
  tijd: string;
  review_reason?: ReviewReason | null;
  comment: string;
  wijziging: Record<string, unknown>;
}

/** Eén Critic-oordeel binnen de herzieningslus, met de instructie die eruit volgde. */
export interface CriticRonde {
  ronde: number;
  aandacht?: Aandacht | null;
  motivatie: string;
  actie: string;              // behoud | vervang | verwijder
  /** Is de instructie ook uitgevoerd? De correctie gebeurt in code (graph-qa's patcher), dus
   *  "de Critic vroeg erom" en "het is gebeurd" zijn twee verschillende feiten. */
  toegepast?: boolean;
  voorstel_klasse: string;
  voorstel_tekst: string;
  tijd: string;
}

/** Critic-oordeel op een element dat de JURIST maakte. Advies; wordt nooit toegepast. */
export interface CriticSuggestie {
  aandacht?: Aandacht | null;
  motivatie: string;
  voorstel_klasse: string;
  voorstel_tekst: string;
  status: string;             // open | geaccepteerd | afgewezen
  tijd: string;
}

/** De herkomst van één agent-ronde: wélk model de voorstellen maakte.
 *  Komt als `run`-SSE-event uit graph-qa en gaat mee in de PUT naar de api, die het op het
 *  document én op elk element vastlegt. Zonder dit is achteraf niet te zeggen waar een markering
 *  vandaan komt — precies wat de export en de latere graaf-promotie nodig hebben. */
export interface AgentRun {
  ronde: number;
  model: string;
  provider: string;
  agent_versie: string;
  critic_rondes: number;
  stop_reden: string;
  tijd: string;
}

/** Waar een fragment stond toen het werd gemaakt: exacte offsets + quote-met-context als vangnet. */
export interface Anker {
  lid: string;
  start: number;
  eind: number;
  voor: string;
  na: string;
  bron_hash: string;
}

export interface AnnotatieElement {
  id: string;
  klasse: string;
  tekst: string;
  lid: string;
  toelichting: string;
  vindplaats: string;
  /** Wie het element AANMAAKTE (agent | mens) — verandert nooit. */
  herkomst: string;
  /** Wie het daarna inhoudelijk aanpaste ("" | agent | mens). */
  gewijzigd_door: string;
  lifecycle: Lifecycle;
  alternatieven: Alternatief[];
  aandacht?: Aandacht | null;
  critic?: string;
  critic_rondes: CriticRonde[];
  critic_suggestie?: CriticSuggestie | null;
  anker?: Anker | null;
  diff: Record<string, { voor: unknown; na: unknown }>;
  beslissingen: Beslissing[];
  /** null = markering van de jurist, of een agent-ronde van vóór de registratie. */
  geproduceerd_door?: AgentRun | null;
}

export interface AnnotatieDocument {
  slug: string;
  user_id: string;
  client_id: string;
  /** Naam van de regeling zoals hij in beeld komt; los van `werkgebied` (het kennisdomein). */
  citeertitel: string;
  werkgebied: string;
  bwbId: string;
  artikel: string;
  lid: string;
  status: DocumentStatus;
  elementen: AnnotatieElement[];
  /** Het productiespoor: elke agent-ronde die aan dit document werkte. */
  runs: AgentRun[];
  created?: string | null;
  updated?: string | null;
}

export interface AuditRecord {
  id: number;
  actor: string;
  actie: string;
  element_id?: string | null;
  detail: Record<string, unknown>;
  tijdstip?: string | null;
}

/** Eén regel in het annotatie-overzicht: naam, voortgang en de JAS-verdeling voor de kleurstrip,
 *  zodat de lijst zonder tweede call kan tonen wat er nog te beoordelen is. */
export interface DocumentSamenvatting {
  slug: string;
  bwbId: string;
  artikel: string;
  lid: string;
  /** Weergavenaam; de server valt terug op werkgebied en dan bwbId. */
  citeertitel: string;
  werkgebied: string;
  status: DocumentStatus;
  aantal_elementen: number;
  te_beoordelen: number;
  per_aandacht: Record<string, number>;
  per_klasse: Record<string, number>;
  /** Leeg = geen agent-ronde geregistreerd (of alleen eigen werk). */
  laatste_model: string;
  updated?: string | null;
}

export interface DocumentCreate {
  bwbId: string;
  artikel: string;
  lid?: string | null;
  citeertitel?: string;
  werkgebied?: string;
}

export interface Wijziging {
  klasse?: string | null;
  tekst?: string | null;
  toelichting?: string | null;
  lid?: string | null;
  // Hoort bij `tekst`: kort de jurist een markering in of breidt hij hem uit, dan schuift de plek
  // mee. Verandert de tekst zonder anker, dan wist de server het oude — een anker dat over het oude
  // fragment gaat zou de markering na herladen naar een ander voorkomen laten springen.
  anker?: Anker | null;
}

export interface BeslissingInvoer {
  type: BeslissingType;
  review_reason?: ReviewReason | null;
  comment?: string;
  wijziging?: Wijziging | null;
}

// --- Unified agent + artikeltekst uit de graaf (graph-qa) --------------------

/** Het doel dat de ophaal-agent heeft opgehaald (uit het `doel`-SSE-event), incl. de opgehaalde tekst
 *  zodat het documentpaneel precies dát toont (ook beleidsregels/divisies zoals '9.1'). */
export interface AgentDoel {
  bwbId: string;
  artikel: string;
  lid: string;
  nummer?: string;
  citeertitel?: string;
  leden_teksten?: { lid: string; tekst: string }[];
}

/** De bepaling die geannoteerd moet worden, meegestuurd bij het starten van een run.
 *
 *  Weet de werkplek hem al (een gekozen kandidaat, een open document), dan slaat de agent de
 *  supervisor én de ophaal-agent over. Het echte winstpunt is niet de besparing maar de zekerheid:
 *  de agent kan dan niet meer bij een ándere bepaling uitkomen dan de jurist aanwees.
 *  Spiegelt `AgentDoel` in `tools/graph-qa/agent/models.py`.
 */
export interface AgentDoelInvoer {
  bwbId: string;
  artikel?: string;
  lid?: string;
  nummer?: string;
  citeertitel?: string;
}

/** Een bepaling die de agent vond bij een ONDERWERP-vraag (uit het `kandidaten`-SSE-event).
 *
 *  De agent kiest er zelf geen: welke bepaling de werkvoorraad in gaat, bepaalt de jurist.
 */
export interface AgentKandidaat {
  bwbId: string;
  artikel: string;
  lid?: string;
  citeertitel?: string;
  fragment?: string;
}

/** Context bij een adviesvraag of een annotatie: waar gaat het over. */
export interface AgentContext {
  slug?: string;
  bwbId?: string;
  artikel?: string;
  lid?: string;
  element_id?: string;
  klasse?: string;
  fragment?: string;
  corpus?: string;
  bestaande_elementen?: { id: string; klasse: string; tekst: string; lid: string; herkomst: string }[];
}

/** Een bron onder een agent-antwoord (uit het `sources`-SSE-event). */
export interface Bron {
  label: string;
  uri: string;
}

/** De uitkomst van de brongetrouwheidstoets op één antwoord (graph-qa `grounding`-event).
 *
 *  `niveau` is de waarde om te tonen, niet `grounded`: **onbepaald** betekent dat het antwoord geen
 *  enkele vindplaats of citaat noemde en er dus niets te controleren viel. Dat als "gecontroleerd"
 *  presenteren zou schijnzekerheid zijn — precies wat dit platform wil vermijden. */
export interface AgentGrounding {
  niveau: "gegrond" | "onbepaald" | "ongegrond";
  grounded: boolean;
  cited: number;
  /** Verwijzingen die niet in de graafresultaten voorkwamen. */
  unsupported: string[];
  /** Als citaat gepresenteerde tekst die niet letterlijk in de opgehaalde tekst staat. */
  niet_letterlijk: string[];
}

/** Artikeltekst uit de graaf (weergave == annotatie-corpus). */
export interface GraafArtikel {
  bwbId: string;
  artikel: string;
  citeertitel: string;
  opschrift: string;
  leden_teksten: { lid: string; tekst: string }[];
}

/** Eén voorgesteld element uit de graph-qa annotatie-SSE (nog niet gepersisteerd). */
export interface VoorstelElement {
  /** Stabiel id van de agent. Hierop matcht de server bij een volgende ronde, zodat beslissingen en
   *  levenscyclus behouden blijven. Ontbreekt het, dan valt de server terug op de tekst. */
  id?: string;
  klasse: string;
  tekst: string;
  lid: string;
  toelichting: string;
  vindplaats: string;
  alternatieven: Alternatief[];
  grounded: boolean;
  aandacht?: Aandacht;   // Critic-oordeel (groen|geel|rood); afwezig = geen Critic-pas
  critic?: string;       // korte Critic-motivatie
  /** Het heen-en-weer met de Critic, één regel per ronde. De api merget ze op rondenummer. */
  critic_rondes?: CriticRonde[];
}

/** Een door de Critic vermoed ontbrekend JAS-element (suggestief; geen span/bron). */
export interface OntbrekendItem {
  klasse: string;
  reden: string;
  /** Het letterlijke fragment dat gemarkeerd zou moeten worden. Ontbreekt als de Critic het element
   *  alleen impliciet in de tekst ziet — dan is het niet toe te voegen (elk element moet letterlijk
   *  in de wettekst staan) en zegt de UI dat ook. */
  tekst?: string;
}

/** Eén agent-beurt als server-object (graph-qa `/v1/runs`).
 *
 *  De run leeft bij de agent, niet in het tabblad: wegklikken of herladen koppelt alleen de kijker
 *  los. `vraag` reist mee omdat een tabblad dat halverwege aanhaakt anders tokens uit het niets
 *  krijgt, en `volgende_seq`/`weggevallen` zeggen waar de eventlog staat zodat aanhaken op het
 *  juiste punt begint. */
export interface RunStart {
  run_id: string;
  conversation_id: string;
  vraag: string;
  status: "loopt" | "klaar" | "gestopt" | "mislukt";
  volgende_seq: number;
  weggevallen: number;
}

// --- Gesprekken (chatgeschiedenis) — afgeleid van api/app/gesprek_contracts.py ---

export type Rol = "user" | "assistant";

/** Eén beurt in een gesprek. Assistent-berichten dragen optioneel denkproces/bronnen, of een
 *  verwijzing naar een annotatie-document (`annotatie_slug` + de Critic-`ontbrekend`-suggesties).
 *
 *  `annotatie_titel` is het leesbare label van dat document op het moment van de beurt. Het bericht
 *  beschrijft zichzelf dus: wordt het document later verwijderd, dan blijft er in de thread een
 *  leesbare kaart staan in plaats van een naamloze verwijzing. Berichten van vóór dit veld leveren
 *  `""` — dat is een lege terugval, geen fout. */
export interface Bericht {
  id?: number;
  rol: Rol;
  tekst: string;
  denk: string;
  bronnen: Bron[];
  annotatie_slug: string;
  annotatie_titel: string;
  ontbrekend: OntbrekendItem[];
  /** Van welke agent-run deze beurt de uitkomst is; de api gebruikt het als idempotentiesleutel,
   *  zodat twee meekijkende tabbladen niet elk hun eigen kopie wegschrijven. */
  run_id: string;
  created?: string;
}

/** Eén chat-gesprek met zijn berichten (volledig geladen). */
export interface Gesprek {
  id: string;
  user_id: string;
  titel: string;
  berichten: Bericht[];
  created?: string;
  updated?: string;
}

/** Lichte lijst-weergave voor de sidebar (chatgeschiedenis). */
export interface GesprekSamenvatting {
  id: string;
  titel: string;
  aantal_berichten: number;
  updated?: string;
}

/** Eén toe te voegen bericht (append). */
export interface BerichtInvoer {
  rol: Rol;
  tekst?: string;
  denk?: string;
  bronnen?: Bron[];
  annotatie_slug?: string;
  annotatie_titel?: string;
  ontbrekend?: OntbrekendItem[];
  run_id?: string;
}

// --- Berichtensysteem --------------------------------------------------------
//
// LET OP — twee soorten "bericht" in deze codebase, met eigen API-domeinen:
//   • `Bericht` / `BerichtInvoer` hierboven = een **chatbeurt** in de werkplek
//     (`/v1/gesprekken/{id}/berichten`).
//   • `BerichtOut` en de rest hieronder = een **release note / aankondiging** die een beheerder
//     publiceert en analisten lezen (`/v1/berichten`).
// De namen komen uit de API; ze verwijzen naar niets gemeenschappelijks.

export type BerichtType = "info" | "update" | "waarschuwing" | "kritiek";

/** Gepubliceerd bericht met leesstatus (voor analisten). */
export interface BerichtOut {
  id: number;
  titel: string;
  inhoud: string;
  type: BerichtType;
  versie: string | null;
  gepubliceerd: boolean;
  gepubliceerd_op: string | null;
  gelezen: boolean;
  created: string;
  updated: string;
}

/** Bericht zonder leesstatus (voor admin-beheerlijst). */
export type AdminBerichtOut = Omit<BerichtOut, "gelezen"> & { aangemaakt_door: string };

export interface OngelezenAantalOut {
  aantal: number;
}

export interface BerichtenPaginaOut {
  items: BerichtOut[];
  totaal: number;
  pagina: number;
  per_pagina: number;
}

export interface AdminBerichtenPaginaOut {
  items: AdminBerichtOut[];
  totaal: number;
  pagina: number;
  per_pagina: number;
}

export interface BerichtAanmakenIn {
  titel: string;
  inhoud: string;
  type: BerichtType;
  versie?: string | null;
}

export interface BerichtPublicatieIn {
  gepubliceerd: boolean;
}
