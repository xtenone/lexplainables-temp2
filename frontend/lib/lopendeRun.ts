// Welke beurt had dit gesprek nog lopen toen je wegging?
//
// Een run leeft in het geheugen van graph-qa. Een deploy of herstart wist dat register — en dan is
// een client die terugkomt met een run-id dat niemand meer kent nergens meer aan te haken. Zonder
// dit spoor zie je dan niets: geen antwoord, geen melding, alleen een gesprek dat halverwege
// ophoudt. Mét dit spoor kan de werkplek zeggen wát er gebeurd is.
//
// Bewust `localStorage` en niet `sessionStorage`: een herlaadbeurt in een nieuw tabblad moet het
// óók weten. En bewust alleen het id — de inhoud van een beurt hoort in de api, niet in de browser.
//
// De logica staat hier als pure functies omdat vitest node-env draait zonder DOM (zie
// `lib/selectie.ts`); het component doet alleen de opslag-aanroepen.

const SLEUTEL = "wa_lopende_run";

/** Wat er in de opslag staat: per gesprek het id van de beurt die liep. */
export type LopendeRuns = Record<string, string>;

export function onthoudRun(huidig: LopendeRuns, gesprekId: string, runId: string): LopendeRuns {
  return { ...huidig, [gesprekId]: runId };
}

export function vergeetRun(huidig: LopendeRuns, gesprekId: string): LopendeRuns {
  const { [gesprekId]: _weg, ...rest } = huidig;
  return rest;
}

/** Wat is er met de vorige beurt van dit gesprek gebeurd?
 *
 *  - `"geen"` — er stond niets open.
 *  - `"afgerond"` — de beurt is netjes vastgelegd; het bericht staat in de geschiedenis. Alleen het
 *    spoor opruimen, geen mededeling: de gebruiker ziet het antwoord gewoon staan.
 *  - `"verdwenen"` — er is geen run meer én geen bericht. Dan is het register weg (herstart) en
 *    hoort dat gezegd te worden, in plaats van een beurt die stilzwijgend nooit afkwam.
 *
 *  De controle op het bericht is wat dit betrouwbaar maakt: een run die afliep terwijl niemand keek
 *  is óók uit het register verdwenen (na de bewaartermijn), maar heeft wél een bericht achtergelaten.
 *  Zonder dat onderscheid zou elke normale afloop als "afgebroken" gemeld worden.
 */
export function standVanVorigeRun(
  bewaardRunId: string | undefined,
  berichtRunIds: readonly string[],
): "geen" | "afgerond" | "verdwenen" {
  if (!bewaardRunId) return "geen";
  return berichtRunIds.includes(bewaardRunId) ? "afgerond" : "verdwenen";
}

/** Wat doe je als de eventstroom van een lopende beurt met een fout eindigt?
 *
 *  - `"negeren"` — er is niets te doen: wíj koppelden zelf los (unmount, van gesprek wisselen), of
 *    het venster is weg. De run draait door bij de agent.
 *  - `"opnieuw"` — de verbinding viel weg. Ook dan draait de run door: hij leeft bij de agent, niet
 *    in dit tabblad. Opnieuw aanhaken vanaf `seq 0` speelt de eventlog terug, dus je mist niets.
 *  - `"melden"` — de fout is `definitief`: opnieuw aanhaken kan per definitie niet slagen. Nu pas
 *    een foutmelding.
 *
 *  Waarom dit een eigen regel is: de werkplek toonde bij elke andere fout dan een `AbortError`
 *  meteen "Er ging iets mis". Bij een deploy — de frontend-container wordt vervangen — betekende dat
 *  een beurt die als mislukt in beeld kwam terwijl hij op dat moment gewoon doorliep en even later
 *  slaagde, mét een opgeslagen bericht bij de api. De client hoorde daar niet over te oordelen.
 *
 *  Er is geen pogingen-cap meer. Die was er ("één poging, anders een molen"), maar hij loste het
 *  verkeerde probleem op: een onderbreking die langer duurde dan die ene poging — een herstart van
 *  graph-qa, een netwerkdip — kwam als definitieve fout in beeld terwijl de beurt gewoon doorliep,
 *  en alleen een herlaadbeurt bracht hem terug. Doorproberen is geen molen zolang het zichtbaar is
 *  (de banner staat er) en de wachttijd oploopt (zie `herstelWachttijd`); wat het wél moest zijn is
 *  begrensd op fouten waar herhalen kans maakt — vandaar `definitief`.
 */
export function naEenGebrokenStream(
  zelfAfgebroken: boolean,
  vensterLeeft: boolean,
  definitief: boolean,
): "negeren" | "opnieuw" | "melden" {
  if (zelfAfgebroken || !vensterLeeft) return "negeren";
  return definitief ? "melden" : "opnieuw";
}

/** Is dit een fout waar opnieuw aanhaken per definitie niet meer bij helpt?
 *
 *  - een fout die de agent zélf stuurde (`error`-event): de beurt is inhoudelijk mislukt, de
 *    eventlog opnieuw afspelen levert dezelfde fout op.
 *  - 401/403: de sessie deugt niet meer. 404: de run bestaat niet meer — het register is leeg na een
 *    herstart, en aanhaken op een run die niemand kent lukt nooit meer.
 *
 *  Al het andere (netwerkfout zonder status, 502/503/504 van de BFF, een stilgevallen stroom) is
 *  tijdelijk tot het tegendeel blijkt.
 */
export function definitieveStroomfout(fout: unknown): boolean {
  const f = fout as { status?: number; agentFout?: boolean } | null;
  if (!f) return false;
  return f.agentFout === true || f.status === 401 || f.status === 403 || f.status === 404;
}

/** Hoe lang wachten vóór de volgende poging? Oplopend: 1,5 → 3 → 6 → 12 → 15 s (plafond).
 *
 *  Meteen opnieuw proberen is bij een herstartende dienst gegarandeerd weer mis, en elke seconde
 *  doorrammen belast een dienst die net overeind krabbelt. Het plafond houdt het herstel wél vlot:
 *  langer dan een kwart minuut stilstaan terwijl de dienst er weer is, is niet uit te leggen.
 */
export function herstelWachttijd(poging: number): number {
  return Math.min(1500 * 2 ** Math.max(0, poging), 15_000);
}

// --- browser-opslag (dun laagje om de pure functies heen) -----------------------------------

export function leesLopendeRuns(): LopendeRuns {
  try {
    const rauw = window.localStorage.getItem(SLEUTEL);
    return rauw ? (JSON.parse(rauw) as LopendeRuns) : {};
  } catch {
    // Privémodus, volle opslag of rommel in de sleutel: dit is een hulpmiddel, geen contract.
    return {};
  }
}

export function schrijfLopendeRuns(runs: LopendeRuns): void {
  try {
    window.localStorage.setItem(SLEUTEL, JSON.stringify(runs));
  } catch {
    /* opslag niet beschikbaar — dan missen we hoogstens de melding */
  }
}

/** Wacht `ms`, maar laat je wekken zodra er reden is om het eerder te proberen.
 *
 *  Twee wekkers, allebei een sterk signaal dat het zin heeft:
 *  - `online` — het netwerk is terug. De volle backoff uitzitten terwijl de verbinding er alweer is,
 *    is precies wat "hij herstelt niet" voelt.
 *  - het tabblad wordt zichtbaar — de gebruiker kijkt weer, en een achtergrondtabblad krijgt zijn
 *    timers van de browser toch al geknepen.
 *
 *  Geeft `false` terug als het venster ondertussen verdween; de aanroeper hoort dan niet opnieuw
 *  aan te haken.
 */
export function wachtMetWekker(ms: number, vensterLeeft: () => boolean): Promise<boolean> {
  return new Promise((klaar) => {
    let af = false;
    const stop = (waarde: boolean) => {
      if (af) return;
      af = true;
      clearTimeout(timer);
      window.removeEventListener("online", wekker);
      document.removeEventListener("visibilitychange", bijZicht);
      klaar(waarde && vensterLeeft());
    };
    const wekker = () => stop(true);
    const bijZicht = () => {
      if (document.visibilityState === "visible") stop(true);
    };
    const timer = setTimeout(() => stop(true), ms);
    window.addEventListener("online", wekker);
    document.addEventListener("visibilitychange", bijZicht);
  });
}
