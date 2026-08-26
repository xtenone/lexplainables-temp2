// Client-side fetch-helpers. Praten UITSLUITEND met de eigen Next.js-origin (/api/**);
// de BFF-laag injecteert het token server-side. Hier dus geen Authorization-header.

import type {
  ApiError,
  ApiTokenCreated,
  ApiTokenOut,
  LlmProfileIn,
  LlmProfileOut,
  LoginVerifyResult,
  MeAccount,
  Role,
  TempPassword,
  TestResult,
  TotpBegin,
  UserCreated,
  UserOut,
} from "./types";
import type {
  AdminBerichtenPaginaOut,
  AdminBerichtOut,
  AgentContext,
  AgentDoelInvoer,
  AgentDoel,
  AgentGrounding,
  AgentKandidaat,
  AgentRun,
  Anker,
  AnnotatieDocument,
  AuditRecord,
  Bericht,
  BerichtAanmakenIn,
  BerichtenPaginaOut,
  BerichtInvoer,
  BerichtOut,
  BerichtPublicatieIn,
  BeslissingInvoer,
  Bron,
  DocumentCreate,
  DocumentSamenvatting,
  Gesprek,
  GesprekSamenvatting,
  GraafArtikel,
  OngelezenAantalOut,
  OntbrekendItem,
  RunStart,
  VoorstelElement,
} from "./types";
import { pathSegment } from "./url";

export async function parseError(res: Response): Promise<ApiError> {
  let detail = res.statusText;
  try {
    const body = await res.json();
    if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  } catch {
    /* geen JSON-body */
  }
  const ra = res.headers.get("Retry-After");
  return { status: res.status, detail, retryAfter: ra ? Number(ra) : undefined };
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw await parseError(res);
  return (await res.json()) as T;
}

function veiligJson(s: string): { answer?: string; detail?: string } | null {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

export function isApiError(e: unknown): e is ApiError {
  return typeof e === "object" && e !== null && "status" in e && "detail" in e;
}

/** De leesbare reden achter een mislukte aanroep.
 *
 *  Let op waaróm dit bestaat: een `ApiError` is een object-literal, géén `Error`-instantie. Een
 *  handler die `e instanceof Error ? e.message : "<generiek>"` schrijft, valt dus bij *elke*
 *  api-fout terug op de generieke tekst — en dan wordt "een agent-voorstel verwerp je" (409)
 *  onzichtbaar achter "de markering is niet gewist". Gebruik deze helper, niet `instanceof`.
 */
export function foutTekst(e: unknown, terugval = "Er ging iets mis."): string {
  if (isApiError(e)) return e.detail;
  return (e as Error)?.message || terugval;
}

// --- Admin: LLM-modelprofielen ----------------------------------------------

export async function listProfiles(): Promise<LlmProfileOut[]> {
  const res = await fetch("/api/admin/profiles", { cache: "no-store" });
  return json<LlmProfileOut[]>(res);
}

export async function saveProfile(name: string, body: LlmProfileIn): Promise<LlmProfileOut> {
  const res = await fetch(`/api/admin/profiles/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<LlmProfileOut>(res);
}

export async function deleteProfile(name: string): Promise<void> {
  const res = await fetch(`/api/admin/profiles/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

export async function setDefaultProfile(name: string): Promise<LlmProfileOut> {
  const res = await fetch(`/api/admin/profiles/${encodeURIComponent(name)}/default`, { method: "POST" });
  return json<LlmProfileOut>(res);
}

export async function testProfile(name: string): Promise<TestResult> {
  const res = await fetch(`/api/admin/profiles/${encodeURIComponent(name)}/test`, { method: "POST" });
  return json<TestResult>(res);
}

// --- Admin: gebruikers ------------------------------------------------------

export async function listUsers(): Promise<UserOut[]> {
  const res = await fetch("/api/admin/users", { cache: "no-store" });
  return json<UserOut[]>(res);
}

export async function createUser(userid: string, email: string, role: Role): Promise<UserCreated> {
  const res = await fetch("/api/admin/users", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userid, email, role }),
  });
  return json<UserCreated>(res);
}

export async function patchUser(userid: string, body: { role?: Role; active?: boolean }): Promise<UserOut> {
  const res = await fetch(`/api/admin/users/${encodeURIComponent(userid)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<UserOut>(res);
}

export async function resetUserPassword(userid: string): Promise<TempPassword> {
  const res = await fetch(`/api/admin/users/${encodeURIComponent(userid)}/reset-password`, { method: "POST" });
  return json<TempPassword>(res);
}

export async function deleteUser(userid: string): Promise<void> {
  const res = await fetch(`/api/admin/users/${encodeURIComponent(userid)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

// --- Admin: genereerbare API-tokens -----------------------------------------

export async function listApiTokens(): Promise<ApiTokenOut[]> {
  const res = await fetch("/api/admin/api-tokens", { cache: "no-store" });
  return json<ApiTokenOut[]>(res);
}

export async function createApiToken(label: string): Promise<ApiTokenCreated> {
  const res = await fetch("/api/admin/api-tokens", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label }),
  });
  return json<ApiTokenCreated>(res);
}

export async function revokeApiToken(id: string): Promise<void> {
  const res = await fetch(`/api/admin/api-tokens/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

// --- Login (pre-check vóór de Auth.js-sessie) -------------------------------

/** Stap A — pre-check: kloppen userid+wachtwoord, en is 2FA vereist? Een vertrouwd apparaat (cookie)
 *  levert direct code "ok". Zet zelf geen sessie. */
export async function loginVerify(
  userid: string,
  password: string,
): Promise<LoginVerifyResult> {
  const res = await fetch("/api/login-verify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userid, password }),
  });
  if (!res.ok && res.status !== 200) {
    return { ok: false, code: res.status === 429 ? "rate" : "invalid", userid: "", email: "", role: "" };
  }
  return (await res.json()) as LoginVerifyResult;
}

/** Stap B — verifieer de 2FA-code op het aparte /login/2fa-scherm via het login-ticket (httpOnly
 *  cookie). `remember` zet de trusted-device-cookie (30 dagen). Zet zelf geen sessie. */
export async function login2fa(
  userid: string,
  totp: string,
  remember: boolean,
): Promise<LoginVerifyResult> {
  const res = await fetch("/api/login-2fa", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userid, totp, remember }),
  });
  if (!res.ok && res.status !== 200) {
    return { ok: false, code: res.status === 429 ? "rate" : "invalid", userid: "", email: "", role: "" };
  }
  return (await res.json()) as LoginVerifyResult;
}

// --- PoC-disclaimer ----------------------------------------------------------

export async function accepteerDisclaimer(): Promise<void> {
  const res = await fetch("/api/disclaimer", { method: "POST" });
  if (!res.ok) throw await parseError(res);
}

/** Bij het uitloggen: de sessiecookie overleeft anders een logout in dezelfde browsersessie. */
export async function wisDisclaimer(): Promise<void> {
  await fetch("/api/disclaimer", { method: "DELETE" }).catch(() => {
    /* uitloggen mag hier nooit op stuklopen */
  });
}

// --- Account (self-service): 2FA --------------------------------------------

export async function getAccount(): Promise<MeAccount> {
  const res = await fetch("/api/account/me", { cache: "no-store" });
  return json<MeAccount>(res);
}

export async function begin2fa(): Promise<TotpBegin> {
  const res = await fetch("/api/account/2fa/begin", { method: "POST" });
  return json<TotpBegin>(res);
}

export async function activate2fa(totp: string): Promise<void> {
  const res = await fetch("/api/account/2fa/activate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ totp }),
  });
  if (!res.ok) throw await parseError(res);
}

export async function disable2fa(totp: string): Promise<void> {
  const res = await fetch("/api/account/2fa/disable", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ totp }),
  });
  if (!res.ok) throw await parseError(res);
}

export async function changePassword(current: string, nieuw: string): Promise<void> {
  const res = await fetch("/api/account/password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ current, new: nieuw }),
  });
  if (!res.ok) throw await parseError(res);
}

// --- Annotatie-workbench -----------------------------------------------------

export async function lijstDocumenten(limit = 200): Promise<DocumentSamenvatting[]> {
  // Eén ruime greep: bij tientallen documenten is client-side zoeken/filteren genoeg, en de lijst
  // moet in één keer sorteerbaar zijn. De api kan limit/offset als het ooit groeit.
  return json<DocumentSamenvatting[]>(
    await fetch(`/api/annotatie/documenten?limit=${limit}`, { cache: "no-store" }),
  );
}

export async function haalDocument(slug: string): Promise<AnnotatieDocument> {
  return json<AnnotatieDocument>(
    await fetch(`/api/annotatie/documenten/${pathSegment(slug)}`, { cache: "no-store" }),
  );
}

export async function verwijderDocument(slug: string): Promise<void> {
  const res = await fetch(`/api/annotatie/documenten/${pathSegment(slug)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

// `maakDocument` en `zetElementen` stonden hier: de browser legde de uitkomst van een agent-beurt
// zelf vast als het `opgeslagen`-event uitbleef. Dat was een tweede implementatie naast
// `agent/beurt.py`, en welke van de twee liep hing af van één SSE-event. Eén schrijver nu — de
// agent — dus de browser heeft die twee routes niet meer nodig. Zet ze niet terug: een eigen
// annotatie voeg je toe met `voegElementToe`, dat is een andere handeling.

/** Voeg een EIGEN markering toe (tekstselectie van de jurist). Aparte route van `zetElementen`:
 *  dat is de uitkomst van een agent-ronde, dit komt er los bij en raakt de rest niet. */
export async function voegElementToe(
  slug: string,
  element: { klasse: string; tekst: string; lid?: string; toelichting?: string; vindplaats?: string; anker?: Anker },
): Promise<AnnotatieDocument> {
  const res = await fetch(`/api/annotatie/documenten/${pathSegment(slug)}/elementen`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(element),
  });
  return json<AnnotatieDocument>(res);
}

/** Verwijder een eigen markering. Agent-voorstellen verwerp je (`beslis` met `reject`); die
 *  verdwijnen niet, zodat het auditspoor laat zien dát er een voorstel was. */
export async function verwijderElement(slug: string, elementId: string): Promise<void> {
  const res = await fetch(
    `/api/annotatie/documenten/${pathSegment(slug)}/elementen/${pathSegment(elementId)}`,
    { method: "DELETE" },
  );
  if (!res.ok) throw await parseError(res);
}

export async function beslis(
  slug: string,
  elementId: string,
  req: BeslissingInvoer,
): Promise<AnnotatieDocument> {
  const res = await fetch(
    `/api/annotatie/documenten/${pathSegment(slug)}/elementen/${pathSegment(elementId)}/beslissing`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(req) },
  );
  return json<AnnotatieDocument>(res);
}

export async function haalAudit(slug: string): Promise<AuditRecord[]> {
  return json<AuditRecord[]>(
    await fetch(`/api/annotatie/documenten/${pathSegment(slug)}/audit`, { cache: "no-store" }),
  );
}

// --- Gesprekken (chatgeschiedenis; per-gebruiker via de BFF-X-User-Id) ------

export async function lijstGesprekken(): Promise<GesprekSamenvatting[]> {
  return json<GesprekSamenvatting[]>(await fetch("/api/gesprekken", { cache: "no-store" }));
}

export async function maakGesprek(titel = ""): Promise<Gesprek> {
  const res = await fetch("/api/gesprekken", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titel }),
  });
  return json<Gesprek>(res);
}

export async function haalGesprek(id: string): Promise<Gesprek> {
  return json<Gesprek>(await fetch(`/api/gesprekken/${pathSegment(id)}`, { cache: "no-store" }));
}

export async function voegBerichtToe(id: string, bericht: BerichtInvoer): Promise<Bericht> {
  const res = await fetch(`/api/gesprekken/${pathSegment(id)}/berichten`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(bericht),
  });
  return json<Bericht>(res);
}

export async function hernoemGesprek(id: string, titel: string): Promise<Gesprek> {
  const res = await fetch(`/api/gesprekken/${pathSegment(id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ titel }),
  });
  return json<Gesprek>(res);
}

export async function verwijderGesprek(id: string): Promise<void> {
  const res = await fetch(`/api/gesprekken/${pathSegment(id)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

/** De callbacks waarmee een beurt binnenkomt. Gedeeld door het starten van een run (`startRun`) en
 *  het aanhaken bij een lopende (`volgRun`) — één contract, twee ingangen. */
export type AgentHandlers = {
    onStatus?: (m: string) => void;
    onReason?: (t: string) => void;
    onToken?: (t: string) => void;
    onSources?: (bronnen: Bron[]) => void;
    /** De brongetrouwheidstoets op dit antwoord. Kwam altijd al binnen als `grounding`-event, maar
     *  werd nergens uitgelezen — dus een niet-onderbouwde verwijzing bleef onzichtbaar. */
    onGrounding?: (g: AgentGrounding) => void;
    onDoel?: (doel: AgentDoel) => void;
    onElement?: (el: VoorstelElement) => void;
    /** De herkomst van deze beurt (model/agentversie); komt vóór de elementen. */
    onRun?: (run: AgentRun) => void;
    onOntbrekend?: (items: OntbrekendItem[]) => void;
    /** Kanttekening van de Critic bij een markering die de JURIST maakte. Nooit een wijziging. */
    onSuggestie?: (s: { element_id: string; aandacht: string; motivatie: string }) => void;
  /** De vraag noemde een onderwerp, geen bepaling: dit zijn de gevonden bepalingen om uit te kiezen. */
  onKandidaten?: (k: AgentKandidaat[]) => void;
  /** Het volgnummer van het laatst verwerkte event. Daarmee haakt een client na een onderbreking
   *  weer aan op precies het juiste punt in plaats van vanaf het begin. */
  onSeq?: (seq: number) => void;
  /** Levensteken: er kwam een event over deze verbinding binnen. Geen inhoud, alleen het feit dát
   *  de stroom loopt — daarop haalt de werkplek de "verbinding weg"-melding weg en zet ze de
   *  herstelteller terug. Zonder dit zou een geslaagd heraanhaken pas zichtbaar zijn aan het eind. */
  onLeeft?: () => void;
  /** Er zijn events weggevallen (de eventlog van de run is gecapt). Toon een gat in plaats van te
   *  doen alsof de tekst compleet is. */
  onGat?: (aantal: number) => void;
  /** De agent heeft de uitkomst zelf vastgelegd (bericht + eventueel annotatiedocument). Komt vlak
   *  vóór het einde. Blijft hij uit, dan schrijft de werkplek zelf weg, zoals vroeger. */
  onOpgeslagen?: (uitkomst: { annotatie_slug: string; run_id: string }) => void;
  /** De beurt slaagde, maar niet alles is bewaard — bv. een markering die de api niet accepteerde.
   *  Geen fout (het meeste staat er wél), maar de jurist hoort te weten dat er iets ontbreekt. */
  onWaarschuwing?: (bericht: string) => void;
};

// --- Runs: de beurt is van de server -----------------------------------------
//
// De run draait bij graph-qa en de browser kijkt mee. Wegklikken, van gesprek wisselen of herladen
// koppelt alleen de kijker los — stoppen doe je met `stopRun`.
//
// Hier stond ook `annoteerAgentStream`: één POST naar `/api/annotatie/agent` die de beurt aan de
// verbinding van dat ene tabblad hing. Die is weg, en niet alleen omdat de run-route hem overbodig
// maakte. Hij stuurde het `conversation_id` uit de browser ongewijzigd door naar graph-qa, waar het
// de thread_id van het agent-geheugen is — zónder te controleren of dat gesprek van deze gebruiker
// was. Met een gespreks-id van iemand anders (die staat gewoon in de URL van de werkplek) las je zo
// diens gesprekshistorie terug. `startRun` hieronder verifieert het eigenaarschap wél, bij de api.

/** Start een beurt. Geeft de run terug, of — als er al een run voor dit gesprek loopt — de
 *  bestaande, zodat de aanroeper daarop aanhaakt in plaats van een tweede te starten.
 *
 *  Die tweede zou niet alleen verwarrend zijn: `conversation_id` is ook de thread_id van het
 *  agent-geheugen, dus twee gelijktijdige beurten schrijven door elkaar heen. */
export async function startRun(
  prompt: string,
  conversationId?: string,
  extra?: { modus?: "auto" | "advies"; context?: AgentContext; doel?: AgentDoelInvoer },
): Promise<RunStart> {
  const res = await fetch("/api/annotatie/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: prompt,
      conversation_id: conversationId,
      ...(extra?.modus ? { modus: extra.modus } : {}),
      ...(extra?.context ? { context: extra.context } : {}),
      // Kennen we de bepaling al, dan hoeft niemand hem meer te zoeken: de agent slaat de
      // supervisor en de ophaal-agent over en annoteert precies deze.
      ...(extra?.doel ? { doel: extra.doel } : {}),
    }),
  });
  if (res.status === 409) {
    // Er loopt al een beurt op dit gesprek. Dat is geen storing, maar deze vraag is óók niet
    // aangenomen — en dat mag de aanroeper niet verwarren met "hij loopt". Gaf `startRun` hier de
    // bestaande run terug, dan verscheen het antwoord op de vórige vraag onder de nieuwe, en ging
    // de nieuwe vraag stilzwijgend verloren.
    const fout = await parseError(res);
    throw { ...fout, loopendeRun: runIdUitDetail(fout.detail) ?? undefined } as RunLooptAlFout;
  }
  return json<RunStart>(res);
}

/** Een 409 van `startRun`: er loopt al een beurt op dit gesprek. `loopendeRun` wijst hem aan, zodat
 *  de werkplek kan aanbieden om daarop aan te haken in plaats van de vraag te verliezen. */
export interface RunLooptAlFout extends ApiError {
  loopendeRun?: string;
}

/** Een fout die de agent zélf over de stroom stuurde (`error`-event), en niet een verbinding die
 *  brak. Het verschil is niet uit de status af te lezen — beide zijn 502 — en het bepaalt wél of
 *  opnieuw aanhaken zin heeft. Zie `definitieveStroomfout` in `lib/lopendeRun.ts`. */
export interface AgentFout extends ApiError {
  agentFout?: true;
}

/** Hoe lang een stroom stil mag vallen voordat we hem als verbroken beschouwen.
 *
 *  sse-starlette stuurt elke ~15 seconden een `:`-heartbeat, dus drie gemiste hartslagen is een
 *  veilige ondergrens. Zonder deze bewaking blijft `reader.read()` eeuwig hangen op een halfopen
 *  socket — geen fout, geen einde, en een werkplek die tot in het oneindige "bezig" toont. */
const STROOM_STILTE_MS = 45_000;

/** Vist het actieve run_id uit een 409-detail. Levert niets op bij een onverwachte vorm — dan is
 *  het gewoon een fout en hoort hij als fout behandeld te worden. */
function runIdUitDetail(detail: string): string | null {
  try {
    const ontleed = JSON.parse(detail) as { run_id?: unknown };
    return typeof ontleed?.run_id === "string" ? ontleed.run_id : null;
  } catch {
    return null;
  }
}

/** Haak aan bij een run en volg hem vanaf `vanaf`. Loskoppelen (abort) laat de run doorlopen —
 *  dat is het hele verschil met de oude stream. */
export async function volgRun(
  runId: string,
  handlers: AgentHandlers,
  vanaf = 0,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/annotatie/run/${pathSegment(runId)}/events?vanaf=${vanaf}`, {
    cache: "no-store",
    signal,
  });
  await verwerkSseStroom(res, handlers);
}

/** Vraag een run te stoppen. Een verzoek, geen feit: de agent-nodes zijn synchroon, dus een lopende
 *  LLM-call maakt zichzelf af en de run eindigt pas op de eerstvolgende grens. */
export async function stopRun(runId: string): Promise<void> {
  const res = await fetch(`/api/annotatie/run/${pathSegment(runId)}/cancel`, { method: "POST" });
  if (!res.ok) throw await parseError(res);
}

/** Loopt er nog een beurt in dit gesprek? Dit vraagt de werkplek bij binnenkomst, zodat een beurt
 *  die tijdens het wegklikken doorliep weer in beeld komt. Faalt stil: geen run kunnen vinden mag de
 *  werkplek niet blokkeren — dan zie je gewoon de gehydrateerde geschiedenis. */
export async function haalActieveRun(gesprekId: string): Promise<RunStart | null | "onbekend"> {
  // Drie uitkomsten, en het verschil telt: `null` betekent "er loopt niets", `"onbekend"` betekent
  // "ik kon het niet vaststellen". Die twee op één hoop gooien leverde een melding op dat je beurt
  // was afgebroken zodra het netwerk één keer hikte — terwijl hij gewoon doorliep.
  try {
    const res = await fetch(`/api/annotatie/run?gesprek=${encodeURIComponent(gesprekId)}`, {
      cache: "no-store",
    });
    if (!res.ok) return "onbekend";
    return (await res.json()) as RunStart | null;
  } catch {
    return "onbekend";
  }
}

/** De SSE-parser: frames uit de body halen en op de handlers afvuren.
 *
 *  Eén implementatie voor beide ingangen, zodat het eventcontract niet op twee plekken uit elkaar
 *  kan lopen. sse-starlette scheidt met \r\n; de CR wordt gestript zodat de framegrens klopt. */
async function verwerkSseStroom(res: Response, handlers: AgentHandlers): Promise<void> {
  if (!res.ok) throw await parseError(res);
  if (!res.body) throw { status: 0, detail: "Geen agentstroom." } as ApiError;

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  // De stiltebewaking. Bewust een verwérpende timer en géén `reader.cancel()`: cancellen levert
  // `done`, en dan zou een halve stroom als een keurig afgeronde beurt eindigen.
  let stilteTimer: ReturnType<typeof setTimeout> | undefined;
  const stilte = () =>
    new Promise<never>((_, mis) => {
      stilteTimer = setTimeout(
        () => mis({ status: 0, detail: "De verbinding viel stil." } as ApiError),
        STROOM_STILTE_MS,
      );
    });
  try {
    for (;;) {
      const { done, value } = await Promise.race([reader.read(), stilte()]);
      clearTimeout(stilteTimer);
      if (done) break;
      // sse-starlette scheidt met \r\n; strip de CR zodat indexOf("\n\n") de frame-grens vindt.
      buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");
      let scheiding: number;
      while ((scheiding = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, scheiding);
        buffer = buffer.slice(scheiding + 2);
        let data = "";
        for (const regel of frame.split("\n")) {
          if (regel.startsWith(":")) continue; // heartbeat
          if (regel.startsWith("data:")) data += regel.slice(5).trim();
        }
        if (!data) continue;
        const ev = veiligJson(data) as
          | {
              type: string;
              message?: string;
              content?: string;
              doel?: AgentDoel;
              element?: VoorstelElement;
              run?: AgentRun;
              items?: OntbrekendItem[];
              sources?: Bron[];
              suggestie?: { element_id: string; aandacht: string; motivatie: string };
              kandidaten?: AgentKandidaat[];
              seq?: number;
              weggevallen?: number;
              annotatie_slug?: string;
              run_id?: string;
              // grounding: `niveau` is nieuw; een oudere agent stuurt alleen `grounded`.
              niveau?: AgentGrounding["niveau"];
              grounded?: boolean;
              cited?: number;
              unsupported?: string[];
              niet_letterlijk?: string[];
            }
          | null;
        if (!ev) continue;
        // Er komt iets door: deze verbinding leeft. Vóór alle inhoudelijke afhandeling, zodat ook
        // een stroom die met een `error`-event begint het herstel eerst als geslaagd afmeldt.
        handlers.onLeeft?.();
        if (typeof ev.seq === "number") handlers.onSeq?.(ev.seq);
        if (ev.type === "gat") handlers.onGat?.(ev.weggevallen ?? 0);
        else if (ev.type === "status") handlers.onStatus?.(ev.message ?? "");
        else if (ev.type === "reason") handlers.onReason?.(ev.content ?? "");
        else if (ev.type === "token") handlers.onToken?.(ev.content ?? "");
        else if (ev.type === "sources" && ev.sources) handlers.onSources?.(ev.sources);
        else if (ev.type === "grounding")
          handlers.onGrounding?.({
            niveau: ev.niveau ?? (ev.grounded === false ? "ongegrond" : "gegrond"),
            grounded: ev.grounded !== false,
            cited: ev.cited ?? 0,
            unsupported: ev.unsupported ?? [],
            niet_letterlijk: ev.niet_letterlijk ?? [],
          });
        else if (ev.type === "doel" && ev.doel) handlers.onDoel?.(ev.doel);
        else if (ev.type === "element" && ev.element) handlers.onElement?.(ev.element);
        else if (ev.type === "run" && ev.run) handlers.onRun?.(ev.run);
        else if (ev.type === "ontbrekend") handlers.onOntbrekend?.(ev.items ?? []);
        else if (ev.type === "suggestie" && ev.suggestie) handlers.onSuggestie?.(ev.suggestie);
        else if (ev.type === "kandidaten") handlers.onKandidaten?.(ev.kandidaten ?? []);
        else if (ev.type === "opgeslagen")
          handlers.onOpgeslagen?.({ annotatie_slug: ev.annotatie_slug ?? "", run_id: ev.run_id ?? "" });
        else if (ev.type === "waarschuwing") handlers.onWaarschuwing?.(ev.message ?? "");
        // `agentFout` onderscheidt dit van een 502 die zegt "de BFF kon graph-qa niet bereiken":
        // die is tijdelijk en mag opnieuw, deze is een uitkomst van de beurt zelf.
        else if (ev.type === "error")
          throw { status: 502, detail: ev.message ?? "Agent mislukt.", agentFout: true } as AgentFout;
      }
    }
  } finally {
    clearTimeout(stilteTimer);
    reader.cancel().catch(() => {});
  }
}

/** Artikeltekst uit de graaf (voedt het workbench-documentpaneel; één bron met de annotatie-corpus).
 *  Met `lid` beperk je de tekst tot dat ene lid. */
export async function haalArtikelGraaf(bwbId: string, artikel: string, lid?: string): Promise<GraafArtikel> {
  const q = `bwb_id=${encodeURIComponent(bwbId)}&artikel=${encodeURIComponent(artikel)}${
    lid ? `&lid=${encodeURIComponent(lid)}` : ""
  }`;
  const res = await fetch(`/api/annotatie/artikel?${q}`, { cache: "no-store" });
  return json<GraafArtikel>(res);
}

/** Rond de annotatie af of open hem weer. Bewust een expliciete handeling: "alle elementen
 *  beslist" is niet hetzelfde als "ik ben klaar". */
export async function zetDocumentStatus(
  slug: string,
  status: "geaccordeerd" | "in_review",
): Promise<AnnotatieDocument> {
  const res = await fetch(`/api/annotatie/documenten/${pathSegment(slug)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return json<AnnotatieDocument>(res);
}

/** Exportformaten van een annotatiedocument. */
export type ExportFormaat = "pdf" | "csv" | "json";

/** Download het annotatiedocument als bestand — ook als de review nog loopt.
 *
 *  De leden gaan mee zodat het rapport de letterlijke wettekst naast de tabel kan zetten
 *  (brongetrouwheid); ontbreken ze, dan laat de api dat blok weg in plaats van iets te
 *  reconstrueren. De bestandsnaam komt uit `Content-Disposition` — de server bepaalt hem, zodat
 *  hij overal gelijk is.
 */
export async function exporteerDocument(
  slug: string,
  formaat: ExportFormaat,
  leden: { lid: string; tekst: string }[] = [],
): Promise<void> {
  const res = await fetch(`/api/annotatie/documenten/${pathSegment(slug)}/export?formaat=${formaat}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ leden }),
  });
  if (!res.ok) throw await parseError(res);

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = bestandsnaamUit(res.headers.get("content-disposition")) ?? `annotatie-${slug}.${formaat}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    // Niet meteen intrekken: Safari breekt de download dan af. Eén tick is genoeg.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function bestandsnaamUit(header: string | null): string | undefined {
  const m = header?.match(/filename="([^"]+)"/);
  return m?.[1];
}

// --- Gebruikersfeedback -------------------------------------------------------

export async function stuurFeedback(body: {
  categorie: string;
  tekst: string;
  pagina?: string;
}): Promise<{ id: number }> {
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return json<{ id: number }>(res);
}

// --- Admin: gebruikersfeedback -----------------------------------------------

export interface FeedbackItem {
  id: number;
  client_id: string;
  userid: string;
  categorie: string;
  tekst: string;
  pagina: string | null;
  created: string;
}

export interface FeedbackPaginaOut {
  items: FeedbackItem[];
  totaal: number;
}

export async function getFeedback(offset = 0, limit = 50): Promise<FeedbackPaginaOut> {
  const res = await fetch(
    `/api/admin/feedback?offset=${offset}&limit=${limit}`,
    { cache: "no-store" },
  );
  return json<FeedbackPaginaOut>(res);
}

export async function getOngelezenFeedbackAantal(): Promise<number> {
  const res = await fetch("/api/admin/feedback/ongelezen-aantal", { cache: "no-store" });
  const data = await json<{ aantal: number }>(res);
  return data.aantal;
}

export async function markeerFeedbackGezien(tot?: string): Promise<void> {
  const res = await fetch("/api/admin/feedback/markeer-gezien", {
    method: "POST",
    headers: tot ? { "Content-Type": "application/json" } : {},
    body: tot ? JSON.stringify({ tot }) : undefined,
  });
  if (!res.ok) throw await parseError(res);
}

export async function verwijderFeedback(id: number): Promise<void> {
  const res = await fetch(`/api/admin/feedback/${encodeURIComponent(id)}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}

// --- Berichtensysteem (analist) ----------------------------------------------

export async function listBerichten(): Promise<BerichtOut[]> {
  const data = await json<BerichtenPaginaOut>(
    await fetch("/api/berichten?ongelezen=true&per_pagina=100", { cache: "no-store" }),
  );
  return data.items;
}

export async function listBerichtenPagina(pagina: number): Promise<BerichtenPaginaOut> {
  return json<BerichtenPaginaOut>(
    await fetch(`/api/berichten?pagina=${pagina}`, { cache: "no-store" }),
  );
}

export async function getOngelezenAantal(): Promise<OngelezenAantalOut> {
  return json<OngelezenAantalOut>(
    await fetch("/api/berichten/ongelezen-aantal", { cache: "no-store" }),
  );
}

export async function markeerAllesGelezen(): Promise<void> {
  const res = await fetch("/api/berichten/lees-alles", { method: "POST" });
  if (!res.ok) throw await parseError(res);
}

// --- Berichtensysteem (admin) ------------------------------------------------

export async function listAlleBerichten(pagina = 1, perPagina = 20): Promise<AdminBerichtenPaginaOut> {
  return json<AdminBerichtenPaginaOut>(
    await fetch(`/api/admin/berichten?pagina=${pagina}&per_pagina=${perPagina}`, { cache: "no-store" }),
  );
}

export async function maakBericht(body: BerichtAanmakenIn): Promise<AdminBerichtOut> {
  return json<AdminBerichtOut>(
    await fetch("/api/admin/berichten", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function updateBericht(id: number, body: BerichtAanmakenIn): Promise<AdminBerichtOut> {
  return json<AdminBerichtOut>(
    await fetch(`/api/admin/berichten/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function zetPublicatie(id: number, gepubliceerd: boolean): Promise<AdminBerichtOut> {
  const body: BerichtPublicatieIn = { gepubliceerd };
  return json<AdminBerichtOut>(
    await fetch(`/api/admin/berichten/${id}/publicatie`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  );
}

export async function verwijderBericht(id: number): Promise<void> {
  const res = await fetch(`/api/admin/berichten/${id}`, { method: "DELETE" });
  if (!res.ok) throw await parseError(res);
}
