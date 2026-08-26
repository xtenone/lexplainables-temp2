# CLAUDE.md — wetsanalyse-frontend

Next.js (App Router) + TypeScript-webapp bovenop de graph-qa-agent (en, voor login/beheer, de
[wetsanalyse-API](../api)). De app **is de werkplek**: `/workbench` (de *Lex-pagina*) — één
chat-achtig gespreksvenster voor **vragen én JAS-annotatie**, live tegen graph-qa (§*Werkplek*). De
home (`/`) leidt daarheen door.

> **Scope: chat-werkruimte.** De app bestaat uit de werkplek, het annotatie-overzicht, de
> login-flow en het instellingenvenster (account, berichten, en voor beheerders modelprofielen, gebruikers,
> API-tokens, berichtenbeheer en feedback). Analyses aanmaken/reviewen/rapporteren hoort niet tot
> de functionaliteit.

Lees ook de projectroot-`CLAUDE.md` en `../api/CLAUDE.md` — de API is de bron van waarheid voor de
datacontracten en de state machine; deze app is een **dunne, server-getokende schil** eroverheen.
Operationele details (lokaal draaien, env-vars, deployment) staan in de `README.md`; dit bestand
beschrijft de architectuurregels die je bij code-werk *in* de frontend niet mag breken.

## Dragend principe — BFF, token blijft server-side

De browser praat **uitsluitend** met de eigen Next.js-origin (`/api/**`). De Route Handlers (de
_backend-for-frontend_) proxyen server-side naar de echte API en injecteren het Bearer-token. Het
token komt dus **nooit** in de browser. Dit lost twee dingen tegelijk op: CORS vervalt (same-origin)
en SSE werkt (de native `EventSource` kan geen `Authorization`-header sturen — de BFF doet dat
server-side en pipet de stream door).

```
Browser ──/api/**──► Next.js (BFF, injecteert token) ──/v1/**──► wetsanalyse-api:3000
```

De **harde scheidingslijn**: alles met een token is server-only.

- `lib/config.ts` (token uit env/`*_FILE`, gecached) en `lib/server.ts` (server→server fetch voor de
  initiële render van Server Components) zijn server-only en mogen **nooit** vanuit een Client
  Component geïmporteerd worden. Doe je dat wel, dan lekt het token naar de bundel.
- Client Components praten alleen via `lib/api.ts` met de eigen `/api/**`-routes — **geen
  Authorization-header** daar.

## Lagen (waar hoort wat)

- `app/api/_lib/proxy.ts` — de kern van de BFF: één `proxy(path, init)`-helper die de upstream-status
  en -body **ongewijzigd** teruggeeft (incl. 401/404/409/429/503 + `Retry-After`/`Location`/
  `Content-Type`-headers), zodat de client correcte foutafhandeling houdt. `init.admin: true`
  injecteert het admin-token i.p.v. het client-token. Verzin in nieuwe routes geen eigen
  fetch-logica — leid alles via deze helper. Hij bewaakt ook de **wachttijd**: Node's `fetch` kent
  geen standaardtimeout, dus een upstream die wél verbindt maar niet antwoordt liet de UI eeuwig in
  zijn laadstand staan. Default 30 s → **504** met een leesbare reden (onbereikbaar blijft 502);
  `timeoutMs` per route hoger waar dat hoort (de modeltest doet een echte LLM-aanroep: 120 s). De **SSE-uitzondering** is de run-events-route
  (`app/api/annotatie/run/[id]/events/route.ts`): geen `proxy()`, maar rauwe passthrough van
  `upstream.body` met `X-Accel-Buffering: no` en `Cache-Control: no-transform` (NPM moet
  proxy-buffering óók uit hebben) — zie §*Werkplek*.
- `lib/server.ts` — server-side helpers voor Server Components / auth (rechtstreeks server→server,
  scheelt een extra self-fetch via de BFF bij de eerste render). Bevat de auth-verificatie
  (`verifyCredentials`/`getAccountStatus`/`getSetupStatus`) die de login-flow gebruikt.
- `lib/api.ts` — alle client-side fetch-helpers naar `/api/**`. Eén plek voor het foutcontract
  (`parseError` → `ApiError` met `retryAfter`); gebruik `isApiError()` in de UI.
- `lib/types.ts` — **met de hand afgeleid van `../api/app/annotatie_contracts.py`**
  (+ `gesprek_contracts.py`) en de bron-van-waarheid voor de TS-kant. Wijzigt het API-contract, werk dit bestand bij (verifieer
  desgewenst tegen `openapi-typescript http://localhost:3000/openapi.json` — zie de README).
  `lib/jas.ts` is de afgeleide presentatie-helper voor de JAS-klasse-weergave (kleur + label uit
  `docs/wetsanalyse/wa-table.png`); brongetrouw geldt ook in de UI — verzin er geen klassen bij.
- `app/**/page.tsx` (Server Components) — data ophalen via `lib/server.ts`; interactie delegeren naar
  een `*Client.tsx` Client Component. `app/page.tsx` (home) doet server-side een `redirect("/workbench")`.
  De werkplek zit in `app/workbench/page.tsx` en de auth-schermen in `app/login/*` + `app/setup` +
  `app/disclaimer`. Account en beheer leven in het **instellingenvenster**:
  `app/instellingen/[[...tab]]/page.tsx` als volle pagina, en `app/@modal/(.)instellingen/…` als
  intercepting route die hem als dialoog over de werkplek heen opent. `app/beheer` en `app/account`
  blijven bestaan als redirect naar de bijbehorende tab.
- `components/` — presentatie. `components/werkplek/` + `components/workbench/` = de chat-werkruimte
  (zie §*Werkplek*). `components/admin/` levert de beheertabs (achter het admin-token):
  **`ProfielenPanel`** met de modelprofiel-editor (`ProfileEditor`), **`UsersPanel`**
  (gebruikersbeheer), **`ApiTokensPanel`**, **`BerichtenBeheerPanel`** (+ `BerichtEditor`) en
  **`FeedbackLijstClient`**. `components/berichten/` heeft het leesbare archief. `components/account/` + `components/auth/` dragen de login/2fa/setup-flow.
  `components/instellingen/` is het instellingenvenster zelf (`InstellingenDialog` = de dialoogschil,
  `InstellingenInhoud` = de tabs; de tabdefinities en de pad-helpers staan in `lib/instellingen.ts`,
  bewust **géén** `"use client"`-module zodat Server Components ze mogen importeren).
  `components/ui/` zijn de primitives.
- **Vormgeving (Rijkshuisstijl, Belastingdienst-stijlvak)** — alle design tokens centraal:
  CSS-variabelen in `app/globals.css` → Tailwind in `tailwind.config.ts` (lintblauw `#154273` +
  hemelblauw `#007bc7` op wit, Fira Sans/Mono als vrij alternatief voor Rijksoverheid Sans).
  De root-font-size is overal 100%: schaal met de Tailwind-tekstklassen, niet met een globale
  krimp. `components/ui/` zijn de primitives (40px-knoppen/velden die onder de `coarse:`-variant
  — `@media (pointer: coarse)`, zie `tailwind.config.ts` — naar 48px groeien voor aanraakbediening,
  platte cards, gecentreerde logobalk met het officiële `public/belastingdienst-logo.svg`). **Knoppen zijn mobile-first**: `Button`/`LinkButton` zijn bewust
  breedte-neutraal (`inline-flex shrink-0`); actie-rijen lopen via `components/ui/ButtonRow.tsx`
  (mobiel volle-breedte gestapeld, `sm:` naast elkaar). Staat een knop buiten een `ButtonRow`
  (bv. naast een invoerveld), geef hem dan `className="w-full sm:w-auto"` en laat de container op
  mobiel stapelen (`flex flex-col … sm:flex-row`) — geen vaste/`flex-wrap`-knoprijen die op smal
  scherm overlopen. De JAS-klassekleuren in `lib/jas.ts` zijn de **exacte labelkleuren uit
  `docs/wetsanalyse/wa-table.png`**.

## Werkplek — de Lex-pagina (`/workbench`)

> **De agent heet Lex.** In beeld is dat de naam: de paginatitel, het label boven elk antwoord
> (`WerkplekClient`), *Vraag Lex*, "voorstel van Lex", "Kanttekening van Lex". In de **code** blijft
> alles `graph-qa` heten (map, image, stack, env-vars) en in het **berichtcontract** blijft de rol
> `assistant` — de naam is presentatie, geen contract. De lege staat van de thread draagt de korte
> zelfbeschrijving; de volledige staat in `tools/graph-qa/agent/prompts.py` (§IDENTITEIT) en de toon
> in `docs/schrijfrichtlijn-lex.md`.

De **Lex-pagina** (`app/workbench/page.tsx`, titel "Lex") → `components/werkplek/WorkbenchShell.tsx`:
een **volledige chat-app-shell** (Claude/ChatGPT-achtig, in Belastingdienst-huisstijl). Er is **geen
globale chrome**: `app/layout.tsx` bevat alleen `Providers`, `{children}` en het `modal`-slot. Elk
scherm draagt zijn eigen kader — de shell-pagina's (`/workbench`, `/instellingen`) zetten zelf
`h-[100dvh] overflow-hidden`, en alles daarbuiten gebruikt `AuthFrame` (zie §*Buiten de schil*).
Bovenaan de shell staat de klikbare **testomgeving-strook**. De shell is twee kolommen:
- **Links de sidebar** (`GesprekSidebar` + `GesprekLijst`): bovenin het Belastingdienst-logo, een
  "Nieuw gesprek"-knop, de **chatgeschiedenis** (per-gebruiker gepersisteerd), en onderin een
  **instellingen/gebruiker**-blok (Account/Beheer + uitloggen). Op `<lg` is dit een off-canvas drawer
  (mobiele topbar met hamburger; scrim/Escape/safe-area) — via **`Dialog` met de `drawer`-variant**,
  niet als eigen constructie: die droeg wél `role="dialog"`/`aria-modal` maar geen focus-trap, dus
  liep Tab achter de scrim door naar de chat eronder. Eén focus-trap in de codebase, zoals `Dialog`
  zelf als uitgangspunt heeft staan.
- **Rechts het chatvenster** (`WerkplekClient.tsx`): één gespreksvenster voor **vragen** (Q&A) én
  **JAS-annotatie**, beide als SSE tegen graph-qa's unified agent. De thread hydrateert uit het actieve
  gesprek en **persisteert elke beurt** naar de api (`/v1/gesprekken/*`); de shell remount het venster
  (via `key`) alleen bij echt van gesprek wisselen, niet wanneer een verse chat bij de eerste beurt zijn
  id krijgt (anders breekt de stream). De graph-qa `conversationId` (thread_id) = het `gesprekId`.
- De **annotatie-review** is een **artefact**: een annotatie-beurt toont een compacte chip in de thread
  die het **`ArtefactPaneel`** opent — een van rechts inschuivend paneel (mobiel bottom-sheet) met de
  annotatie-sub-UI uit `components/workbench/`: **`DocumentPaneel`** highlight de **letterlijke**
  fragmenten (`segmenteer` + `lib/jas.ts:jasStyle`; substring-terugvinden) en **`ReviewQueue`** de
  decision-cards (aandacht-as 🟢🟡🔴, voortgangsteller; edit/reject vragen een `review_reason`).
- **Drie backends, frontend orkestreert:** de **chatgeschiedenis via de api** — BFF
  `app/api/gesprekken/*` → `/v1/gesprekken/*` via `proxy()`, mét de vertrouwde `X-User-Id` uit de sessie
  (client-helpers `lijstGesprekken`/`maakGesprek`/`haalGesprek`/`voegBerichtToe`/`hernoemGesprek`/
  `verwijderGesprek`). **Twee stores op dezelfde `conversation_id`**: de UI-historie staat in de API, het
  **agent-geheugen** in graph-qa's checkpointer — `verwijderGesprek` wist béíde (de BFF-DELETE roept ná de
  API-delete óók graph-qa `DELETE /v1/conversations/{id}` aan, best-effort). Het **live agent-verkeer via graph-qa** — BFF
  `app/api/annotatie/run/**` (starten/meekijken/stoppen) met `graphQaBaseUrl()` + `GRAPH_QA_TOKEN`
  én de vertrouwde `X-User-Id` (client-helpers `startRun`/`volgRun`/`stopRun` in `lib/api.ts`); de
  events-route is de SSE-passthrough. Het documentpaneel haalt de artikeltekst via
  `app/api/annotatie/artikel/route.ts` → graph-qa `GET /v1/artikel` (`haalArtikelGraaf`). De **persistente
  review-state via de api** — BFF `app/api/annotatie/documenten/*` → `/v1/annotatie/*` via `proxy()`, mét
  de vertrouwde `X-User-Id` uit de sessie (annotatie-documenten zijn **per-gebruiker gescopet**, net als
  de gesprekken). Types in `lib/types.ts` (afgeleid van `api/app/annotatie_contracts.py`).
- **Config:** `GRAPH_QA_URL` (intern, default `http://graph-qa:8080`, via `graphQaBaseUrl()`) +
  `GRAPH_QA_TOKEN(_FILE)` — de frontend moet graph-qa op het gedeelde docker-netwerk kunnen
  bereiken (`lib/config.ts`).

### De tijdlijn van een annotatie

Een annotatiebeurt duurt 60-90 seconden. graph-qa stuurt daarin per fase een `status`-regel
(supervisor → ophaal-agent → annoteerder ⇄ Critic → herziening → klaar); `onStatus` plakt die als
`· <regel>` aan `denk`, en `DenkProces` toont ze **live** onder de lopende beurt.

Zodra de beurt een annotatie blijkt, ging dat spoor eerder verloren: het antwoord-item werd vervangen
door de chip. Nu draagt het `annotatie`-item een `denk`-veld, staat de tijdlijn ingeklapt boven de
chip als *"Zo is dit tot stand gekomen"*, en wordt hij met de beurt bewaard (`denk` bestond al in
`BerichtInvoer`) en bij hydratatie teruggehaald. Bij een platform dat om herleidbaarheid draait hoort
achteraf te kunnen zien hoe een annotatie tot stand kwam.

### Annotaties staan los van de gesprekken (`/annotaties`)

Een annotatie was alleen te vinden via het gesprek waarin hij gemaakt was; verdween dat gesprek, dan
bleef het document onbereikbaar in de database staan. Nu is het artefact een eersteklas object, naar
het model van Claude's artifacts-tab: **een ingang in de sidebar die het hoofdgebied vult — de
sidebar blijft staan**, je stapt niet uit de app.

- **`components/werkplek/AppSidebar.tsx`** bezit de gesprekkenlijst (laden, hernoemen, verwijderen)
  en de mobiele drawer, en wordt gedeeld door `WorkbenchShell` en de annotatiepagina's. De handlers
  verschillen per scherm: in de werkplek wisselt een klik van gesprek in lokale state, op
  `/annotaties` navigeert hij naar `/workbench?gesprek=<id>`. `WorkbenchShell` verhoogt
  `verversSignaal` als een beurt een gesprek aanmaakt — de lijst woont daar niet meer.
- **Elk scherm met `AppSidebar` moet de drawer openen.** Onder `lg` is de sidebar een `hidden`-kolom
  en verschijnt de drawer alléén als het scherm `drawerOpen` + `onDrawerSluit` doorgeeft. De
  annotatiepagina's deden dat niet, en daar was op een half scherm dus géén navigatie: geen
  gesprekken, geen account, geen uitloggen. De hamburger zit nu in de gedeelde
  **`components/werkplek/MobieleTopbar.tsx`**, gebruikt door alle drie de schermen, en
  `components/werkplek/sidebar.test.ts` bewaakt dat er geen vierde scherm zonder aankomt.
- **`/annotaties`** (`components/annotaties/AnnotatiesClient.tsx`) heeft twee weergaven op één lijst:
  *te doen* (werkvoorraad: rood → geel → langst stil) en *alles* (per regeling gegroepeerd). De
  stand staat in de URL (`?weergave=alles`, via `replace` — een weergavewissel is geen stap in de
  geschiedenis). De kaart toont de **JAS-kleurstrip**: de klasseverdeling als balk, waar Claude een
  thumbnail zou tonen.
- **De sorteer-, groepeer- en zoeklogica staat in `lib/annotatieOverzicht.ts`**, niet in het
  component: vitest draait node-env zonder DOM, dus alleen pure helpers zijn testbaar — dezelfde
  reden die `lib/selectie.ts` al noemt.
- **`/annotaties/[slug]`** toont het artefact op eigen benen. Bewust zonder `onVraag` (er is geen
  chatveld om een vraag in klaar te zetten — daarvoor is *Openen in de werkplek*) en zonder
  `ontbrekend` (dat hoort bij een chatbeurt, niet bij het document).

**Eén inhoud, twee schillen.** `components/werkplek/ArtefactInhoud.tsx` draagt de wettekst, de
reviewlijst en alle handlers; `ArtefactPaneel` is nog slechts de `Dialog`-schil eromheen en de
annotatiepagina is de tweede schil — hetzelfde patroon als `DisclaimerClient` en
`InstellingenInhoud`. Let op **Escape**: dat hing aan `Dialog.onEscape`, maar die schil bestaat niet
altijd meer. De inhoud handelt het nu zelf af (selectie → bedieningsrij → gekozen element →
`onSluiten`), en `ArtefactPaneel` geeft `Dialog` daarom een **no-op** `onEscape` mee. Zou die er ook
op reageren, dan sprong Escape in één klap door alle lagen heen.

**Het kruisje staat altijd rechtsboven.** De kop van `ArtefactInhoud` is twee vaste regels: titel +
sluitknop, daaronder de acties (status, exporteren, afronden) rechts uitgelijnd. In één wrappende rij
verhuisde het kruisje mee met de knoppen zodra de ruimte krap werd, en dan stond het op een telefoon
ineens tussen *Exporteren* en *Afronden*. Sluiten is de uitweg en die zoek je op één plek — dezelfde
plek als in `InstellingenDialog`, `DisclaimerDialog`, `FeedbackDialoog` en de gesprekkendrawer, met
hetzelfde icoon (viewBox 20, `strokeWidth` 1.6). De prijs is een regel hoogte op een breed scherm.

**Afronden** zit als knop in de kop van `ArtefactInhoud` (dus in beide schillen) en zet de
documentstatus via `zetDocumentStatus`. Expliciet, want "alle elementen beslist" is niet hetzelfde
als klaar zijn; heropenen kan altijd. Afronden **bevriest de hele annotatie**
(`isDocumentVergrendeld`): de handlers vallen stil, de selectie-popover en de ontbrekend-knoppen
verdwijnen, `a`/`x`/`c` doen niets meer en er staat een uitleg-melding boven de lijst. De api
weigert die mutaties tóch met een 409 — de UI laat het slot zien in plaats van die fout af te
wachten, want een knop die alleen nog een foutmelding oplevert is erger dan geen knop.

### Buiten de schil: één kaart

Alles wat geen app-schil is — inloggen, 2FA, de eerste beheerder, de blokkerende disclaimer en de
fout-/laadpagina's — gebruikt **`components/auth/AuthFrame.tsx`**: een gecentreerde kaart op
`bg-surface` met het logo erboven, in dezelfde vormtaal als de dialogen. De oude documentopmaak
(`SiteHeader`, `SiteNav`, `SiteFooter`, `AppMain`, `lib/appShell.ts`) is **weg**; die navigatiebalk
wees naar plekken die inmiddels in de sidebar zitten. Bewust geen namaak-werkplek achter het
inlogscherm: een lege, vervaagde app leest als "hij laadt", niet als "log eerst in".

**De app-schil scrollt niet mee — ook niet op mobiel.** De body is `min-h-[100dvh]` en niet alleen
`min-h-screen`: `100vh` is op mobiel de viewport *zonder* adresbalk, dus zolang die balk in beeld
staat is de body hoger dan wat je ziet en kan het document zelf scrollen — waarna de
testomgeving-strook en de mobiele topbar wegschuiven terwijl de schil eronder juist vaststaat.
`100dvh` volgt de zichtbare hoogte; `min-h-screen` blijft ervóór staan als terugval. Daarnaast staat
`overscroll-behavior: contain` op elke scroller (`globals.css`): bereikt een paneel zijn einde, dan
gaf de browser de scroll door aan het document eronder, en dan bewogen die stroken alsnog
(rubber-banding op iOS, pull-to-refresh op Android).

`app/global-error.tsx` blijft een uitzondering met inline stijl en hardcoded huisstijlkleuren — die
boundary vervangt de hele document-boom en kan de app-CSS niet veronderstellen.

**Een venster is zo hoog als zijn inhoud, tenzij die wisselt.** `Dialog` kent daarvoor twee
gecentreerde vormen: `center` houdt een vaste hoogte aan (42rem) en is bedoeld voor het
instellingenvenster, dat anders bij elke tabwissel van formaat zou springen; `compact` groeit mee met
de inhoud tot een plafond en is bedoeld voor een formulier of een lap tekst. De feedbackdialoog stond
op `center` en had daardoor een halve pagina wit onder de verzendknop — op mobiel claimde hij zelfs
94% van het scherm voor drie velden. Feedback en voorwaarden gebruiken nu `compact`.

**De disclaimer heeft twee schillen, één tekst.** De edge-gate (`auth.config.ts` → `vereistAkkoord`)
stuurt je zonder akkoord naar `/disclaimer`: dat is de **blokkerende** volle pagina in `AuthFrame`.
Klik je de teststrook aan vanuit de werkplek, dan onderschept `app/@modal/(.)disclaimer/page.tsx` dat
pad en opent `DisclaimerDialog` over de werkplek heen — zelfde `DisclaimerClient`, andere schil, en je
verlaat je gesprek niet. Verander je de tekst, dan verander je hem dus op één plek.

**In de dialoogschil sluit je met `router.back()`, nooit met een link.** `DisclaimerClient` krijgt
daarvoor `onSluiten`; kruisje, achtergrondklik, Escape en de knop onderin lopen door dezelfde functie.
Er stond een `LinkButton href="/"` onderin, en dat sluit een intercepting-route-modal juist niet: het
modal-slot houdt zijn toestand vast bij een soft navigation, en `/` leidt bovendien door naar
`/workbench`. Je hield de popup én kreeg er een history-entry bij, waarna het kruisje je terugbracht
náár de voorwaarden — op mobiel, waar de dialoog het hele scherm vult, zat je dan vast.

### Berichten en feedback

Twee kleine domeinen die aan de app-shell hangen, niet aan de oude paginanavigatie:

- **Berichten** (release notes) — `BerichtenPanel` is de bel in de **sidebar-kop** met een
  ongelezen-badge; het archief is de niet-admin tab `/instellingen/berichten`. Let op de naamval:
  `Bericht`/`BerichtInvoer` in `lib/types.ts` zijn **chatbeurten**, `BerichtOut` en familie zijn
  release notes — twee losstaande API-domeinen (`/v1/gesprekken/…/berichten` vs `/v1/berichten`).
- **Feedback** — `FeedbackDialoog` opent vanuit het gebruikersmenu onderin de sidebar. Bewust
  **geen zwevende knop** zoals elders gebruikelijk: die valt over de chat-invoer van de werkplek.
  De ongelezen-teller voor beheerders zit als badge op de feedbacktab (`TabDef.badge`).

Beide panelen halen hun teller periodiek/bij openen op en falen **stil**: een hapering mag de
werkplek niet blokkeren, de badge is een hint.

### Annoteren op onderwerp

Noemt de vraag een onderwerp in plaats van een bepaling, dan komt er een `kandidaten`-event in plaats
van `doel`/`element`: de thread toont een keuzelijst (`KandidatenKeuze`), en één klik stuurt
`kandidaatPrompt(k)` als nieuwe beurt in — **mét `doelVanKandidaat(k)` als gestructureerd `doel`**.
Daarmee slaat de agent de supervisor én de ophaal-agent over (~3-5 LLM-calls minder) en, belangrijker,
kán hij niet meer bij een andere bepaling uitkomen dan de jurist zojuist aanwees. De prompt blijft
daarnaast bestaan als leesbare vraag in de thread, mét het bwbId erin voor het geval een beurt tóch
zonder doel loopt. Zelfde patroon geldt voor elke andere plek waar de werkplek de bepaling al kent:
geef `doel` mee aan `startRun`. Een **adviesvraag** draagt nooit een doel — die route annoteert niet. Er is bewust géén "annoteer ze allemaal": elke annotatie is
een eigen document met een eigen review. De kandidaten zitten niet in het berichtcontract van de api;
wat na een herlaadbeurt overblijft is de opsomming uit `kandidatenAlsTekst`.

### De artefact-werkbank

Vanaf **1280px** (`lib/useBreedScherm.ts`) staat het artefact als **eigen kolom naast de chat** in
plaats van eroverheen: `Dialog` heeft daarvoor de variant **`kolom`** — geen backdrop, geen
`aria-modal` en géén focus-trap (die zou je opsluiten terwijl de chat er juist naast bereikbaar moet
zijn); Escape sluit in alle varianten. Daaronder blijft het de bestaande `side`-sheet. De splitsing
zit in `WerkplekClient` zelf en niet in `WorkbenchShell`, anders moeten `docs`/`infos` en alle
handlers omhoog en weer terug omlaag.

Binnen het artefact hebben **wettekst en reviewlijst elk hun eigen scroll** (tekst `max-h-[45%]`
bovenin). Eén gedeelde scroller liet de tekst uit beeld lopen zodra je verderop in de lijst kwam.
Selecteren scrolt **beide kanten op** in beeld: de markering in de tekst (`DocumentPaneel`) én de
kaart in de lijst (`ReviewQueue`), met `prefers-reduced-motion` gerespecteerd.

- **De kaart is compact**; details (toelichting, Critic-motivatie, alternatieven, adviesdraadje,
  opmerking) vouwen open bij selectie. Eén begrip stuurt alles: `actief`. Een **openstaande
  kanttekening** blijft ook ingeklapt zichtbaar — dat signaal mag je niet missen.
- **Eén vaste volgorde** (`sorteerReview`): de canonieke **JAS-tabelvolgorde** (`jasVolgorde` uit
  `lib/jas.ts`) → lid (numeriek!) → plek in de tekst → invoervolgorde. Géén van die sleutels verandert
  door reviewen; eerder woog aandacht en voortgang het zwaarst, waardoor een goedgekeurd element naar
  achteren sprong en je je plek kwijtraakte. Scherpstellen doen de filters: *alles* / *te beoordelen*
  / *met aandacht*. De positie per element komt uit `ArtefactPaneel`, dat hem in dezelfde lus berekent
  als de zwevende markeringen — één `vindPositie`, dus lijst en tekst spreken elkaar nooit tegen.
- **Zwevende markeringen worden benoemd.** Is een fragment niet meer in de tekst te vinden
  (`vindPositie` → `-1`), dan verdween de markering eerder stilzwijgend. Nu staat het op de kaart en
  in de teller. (Zelfde les als Hypothesis' "orphans".)
- **Toetsenbord**: `j`/`k` (of ↓/↑) door de getoonde lijst, `a` akkoord, `x` verwerpen, `c` klasse,
  `Escape` loslaten. De listener doet **niets zolang de focus in een invoerveld staat** — anders keur
  je iets goed door "a" te typen in een toelichting. Na `Akkoord` springt de selectie door naar het
  volgende dat nog aandacht vraagt; knop en toets lopen via dezelfde `onAkkoord`.
- De **volgorde en de open bedieningsrij leven in `ArtefactPaneel`**, niet in de lijst: zo doorloopt
  het toetsenbord gegarandeerd dezelfde volgorde als je ziet, en staat er nooit op twee kaarten
  tegelijk een rij open.

### Eén gesprek: vragen gaan altijd via het centrale venster

De reviewkaart had een eigen mini-chat (`AdviesDraadje`). Die bestond alleen omdat het artefact
modaal was; nu het ernaast staat is hij **verwijderd**. In plaats daarvan zet *Vraag Lex* op
de kaart een vraag klaar in het chatveld:

- `WerkplekClient` houdt `vraagOver` (slug + element). Zolang dat staat toont een **chip** boven het
  invoerveld waar de vraag over gaat, en gaat de beurt met `modus: "advies"` + `vraagContextVan(...)`.
  De chip verdwijnt na het versturen — anders wordt je vólgende vraag ongemerkt ook een adviesvraag.
- **Drie vragen staan er alvast boven** (`vraagSuggesties` in `lib/annotatie.ts`): *waarom deze
  klasse*, *klopt de afbakening*, en — als de agent een alternatief voorstelde — *waarom die andere
  klasse dan niet*. Die derde past zich aan, want dáár zit het verschil per element. Eén klik stuurt
  de vraag meteen; ze verdwijnen zolang er een beurt loopt, want een tweede vraag zou toch worden
  afgewezen (er loopt al een run op dit gesprek). Een leeg veld met "Wat wil je weten over deze
  markering?" is een open vraag op het moment dat je juist snel wilt beoordelen.
- Het antwoord is een gewone beurt en krijgt daarmee **bronnen, grounding en de kopieerknop**, die het
  draadje in de kaart geen van alle had.
- De chip is UI-state en reist niet mee naar de api; het bewaarde bericht krijgt daarom een
  contextregel (`Bij <klasse> — "<fragment>" (art. 36): <vraag>`), zoals `kandidatenAlsTekst`.
- Op een **smal scherm** sluit het artefact al bij de klik op *Vraag Lex*, niet pas bij het
  versturen. Daar ligt het paneel over de chat, dus anders lijkt de knop niets te doen: de chip met
  de markering en het invoerveld staan erachter, en je typt in een veld dat je niet ziet. Het
  versturen sluit het nog een keer, als vangnet voor wie het paneel intussen opnieuw opende — dan
  wint het antwoord, dat je wilt zien binnenkomen. De focus op de textarea blijft in dezelfde
  gebeurtenis als de klik staan: iOS opent het toetsenbord alleen binnen een gebruikersgebaar.

**De beurt is van de server, niet van dit tabblad.** Een lopend antwoord hing aan de SSE-verbinding
van het venster: van gesprek wisselen, naar `/annotaties` lopen of herladen brak hem af. Nu draait de
beurt als **run** bij graph-qa (`POST /api/annotatie/run` → `startRun`) en kijkt de werkplek mee
(`volgRun` op `/api/annotatie/run/[id]/events`). Vier regels om niet te breken:

- **Unmount koppelt alleen los.** `afbrekenRef.current?.abort()` beëindigt de kijker, niet de run.
  Een `AbortError` in `volgBeurt` is dáárom géén einde: niets bewaren, het echte antwoord komt later.
- **Bij binnenkomst haken we weer aan** (`hervatBeurt` na de hydratatie): loopt er nog een beurt, dan
  komt hij vanaf `seq 0` terug in beeld. Alleen bij status `loopt` — een afgeronde beurt staat al in
  de gehydrateerde geschiedenis, en twee keer tonen is erger dan missen.
- **Stoppen is een verzoek** (`stopRun`), geen dichtvallende socket. De agent stopt op een
  nodegrens, dus dat kan tientallen seconden duren; de knop blijft daarom in de `stopt`-stand staan.
  Stoppen vóór de voorstellen levert er écht nul op — het bericht zegt dat, in plaats van een half
  resultaat te suggereren.
- **Na een herstart van de agent is het run-register leeg.** `lib/lopendeRun.ts` onthoudt per gesprek
  welk run-id er liep; bij binnenkomst zonder lopende run bepaalt `standVanVorigeRun` of de beurt
  gewoon is afgerond (het bericht met dat `run_id` staat in de geschiedenis) of écht verdwenen is.
  Alleen in dat tweede geval komt er een melding. Zonder die controle zou elke normale afloop als
  "afgebroken" gemeld worden.
- **`run_id` reist mee naar de api** bij het bewaren van de assistent-beurt. Kijken er twee tabbladen
  mee, dan landt de uitkomst tóch één keer (de api dedupliceert erop).
- **De agent schrijft weg, de werkplek nooit.** graph-qa stuurt vlak vóór het einde een
  `opgeslagen`-event met de `annotatie_slug`; de client haalt het document dán bij de api op
  (`toonVastgelegdeBeurt`). Blijft dat event uit terwijl er wél markeringen waren, dan is dat een
  **storing** en toont de werkplek dat als zodanig — er is geen tweede schrijfpad meer.
  Dat pad bestond wel (`maakDocument` + `zetElementen` vanuit de browser, met eigen artikelophaling
  en eigen titelopbouw), en welke van de twee liep hing af van de aan/afwezigheid van één SSE-event;
  bij een gedeeltelijk falen leverde dat een tweede document op. Beide client-helpers zijn daarom
  weg uit `lib/api.ts`. Zet ze niet terug: een eigen markering voeg je toe met `voegElementToe`,
  dat is een andere handeling. Een graph-qa **zonder** api-koppeling legt niets meer vast en meldt
  dat nu zelf met een `error`-event (`agent/beurt.py`).
- **Een weggevallen verbinding is geen mislukte beurt.** Alleen een `AbortError` (wij koppelen zelf
  los) werd als "geen einde" behandeld; elke andere fout zette meteen "Er ging iets mis" neer. Bij
  een deploy — de frontend-container wordt vervangen — betekende dat een beurt die als mislukt in
  beeld kwam terwijl hij doorliep, slaagde en zijn bericht bij de api achterliet. `volgBeurt` haakt
  nu **één keer** opnieuw aan (`naEenGebrokenStream` in `lib/lopendeRun.ts`, na 1,5 s, met
  `vanaf: 0` zodat de eventlog wordt teruggespeeld); pas als die herkansing op is, of als het
  venster weg is, komt er een foutmelding. Eén poging, niet meer: is de dienst echt onbereikbaar,
  dan is doorproberen een molen die de gebruiker niets vertelt.

De BFF stuurt de identiteit als **`X-User-Id`-header** mee op álle run-routes, en verifieert bij het
starten eerst bij de api of dit gesprek van jou is — `conversation_id` is ook de thread_id van het
agent-geheugen, dus zonder die controle kon een vreemd gespreks-id een vraag in andermans geheugen
injecteren. Dat is een vertrouwensgrens en geen Dat is een vertrouwensgrens en geen
gemak: graph-qa schrijft namens die gebruiker, dus wie de identiteit zelf zou mogen meesturen,
schrijft in andermans gesprek.

**Foutmeldingen lopen via `foutTekst` uit `lib/api.ts`, nooit via `e instanceof Error`.** Een
`ApiError` is een object-literal, dus die test is altijd onwaar en verving elke serverreden door een
generieke zin — "een agent-voorstel verwérp je" (409) werd zo onzichtbaar achter "de markering is
niet gewist".

Bij een 409 op `startRun` (er loopt al een beurt op dit gesprek) haakt de client aan bij de bestaande
run in plaats van te falen: twee gelijktijdige beurten zouden door elkaar in het agent-geheugen
schrijven.

**Er is nog één weg naar de agent, en dat is met opzet.** `annoteerAgentStream` en zijn route
`app/api/annotatie/agent` zijn verwijderd. Die stuurden het `conversation_id` uit de browser
ongewijzigd door naar graph-qa — waar het de thread_id van het agent-geheugen is — zonder te
controleren of het gesprek van deze gebruiker was; met andermans gespreks-id (dat staat in de URL van
de werkplek) las je zo diens historie terug. Zet er geen tweede ingang naast: elk pad dat een
`conversation_id` aanneemt, hoort eerst bij de api te verifiëren van wie dat gesprek is, zoals
`app/api/annotatie/run/route.ts` doet.

**Een afgekeurd citaat wordt in de tekst zelf aangewezen.** `grounding.niet_letterlijk` ging alleen
naar het blok ónder het antwoord, en dat blok slaat iedereen op den duur over — terwijl je in de
tekst naar een passage kijkt die er betrouwbaar uitziet omdát er aanhalingstekens omheen staan.
`Markdown` neemt daarom `nietLetterlijk` aan en wikkelt elke treffer in een `<mark>` (aandacht-geel
uit de huisstijl, plus een stippellijn en een `sr-only`-toelichting, zodat het signaal niet alleen
aan kleur hangt). De transformatie is een **rehype-plugin op de hast-boom**, niet op de
bron-markdown: zo komt er geen teken in de tekst die de jurist zou meekopiëren en blijft de opmaak
zoals het model hem bedoelde. Matchen gaat letterlijk — wijkt de weergave af van wat de controle
vergeleek (die normaliseert witruimte), dan markeren we liever niets dan het verkeerde stuk, en
noemt het blok eronder de passage alsnog. Logica in `lib/markering.ts`, getest zonder DOM.

**Brongetrouwheid staat onder het antwoord** (`Brongetrouwheid` in `WerkplekClient`). graph-qa stuurt
per beurt een `grounding`-event; dat kwam altijd al binnen maar werd door niemand uitgelezen, dus een
niet-onderbouwde verwijzing bleef onzichtbaar. Het blok zwijgt bij `niveau: "gegrond"` — een groen
vinkje bij élk antwoord leert mensen erover heen te kijken — en spreekt in twee gevallen: **ongegrond**
(een verwijzing die niet uit de graaf kwam, of een citaat dat niet letterlijk in de opgehaalde tekst
staat) en **onbepaald** (het antwoord noemde geen vindplaats en geen citaat, dus er viel niets te
controleren). Dat laatste is nadrukkelijk geen goedkeuring; toon het dus niet als groen. De uitkomst
reist niet mee in het berichtcontract, maar de bijbehorende statusregel staat in `denk` en blijft na
herladen in de tijdlijn terug te vinden.

**Niets faalt meer stil.** Het artefact openen toont een laadstand en bij een fout een `Melding` met
*Opnieuw proberen* (voorheen: een klik waar letterlijk niets van gebeurde als de graaf plat lag). Een
mislukte beslissing landt in de `Melding` ván het artefact — `WerkplekClient.beslissing` gooit hem
door en `ArtefactPaneel.beslis`/`wis` vangen hem — niet meer als chatbericht in de thread.

**Een verwijderde annotatie is een toestand, geen fout.** Een bericht verwijst met een kale
`annotatie_slug` naar een document — er is géén foreign key, dus verwijderen via `/annotaties` laat
die verwijzing dangling achter. `isVerwijderd` (`lib/annotatie.ts`) scheidt de 404 van een echte
storing: 404 → de chip wordt een **tombstone** (grijs, doorgestreepte titel, "Deze annotatie is
verwijderd", link naar `/annotaties`) en een neutrale `Melding type="uitleg"` **zonder** *Opnieuw
proberen*; al het andere houdt de rode melding mét retry. Dat de kaart zichzelf nog kan benoemen komt
doordat het bericht zijn eigen label draagt: **`annotatie_titel`** in het berichtcontract, gevuld met
`annotatieTitel(doc)` op het moment van de beurt. Berichten van vóór dat veld vallen terug op
"Annotatie". Bewust géén cascade server-side: het gesprek is een verslag van wat er gebeurde en dat
herschrijf je niet — en het zou bestaande dangling rijen toch niet oplossen. Zelfde afhandeling op
`/annotaties/[slug]`.

**De annotatie blijft bereikbaar** via een balk boven de chat (`art. 36 · 10 elementen · 3 te
beoordelen · Openen`) zodra het paneel dicht is; de chip in de thread scrolt immers weg. Verwijderde
documenten slaat die balk over.

**"Mogelijk ontbrekend" is werkvoorraad, geen mededeling** (`components/workbench/OntbrekendLijst.tsx`).
Staat er een letterlijk fragment bij dat in de tekst voorkomt → *Toevoegen als \<klasse\>*, één klik,
met anker. Anders zegt het kaartje waaróm het niet kan (geen fragment aangewezen, of het fragment
staat niet letterlijk in de tekst). Toegevoegde items tonen "✓ inmiddels gemarkeerd" en tellen niet
meer mee; is alles afgehandeld, dan verdwijnt het blok.

**Bewust géén "wegleggen".** Dit is informatie, geen takenlijst. Zo'n knop suggereerde een
afhandeling die nergens landde (sessie-only, zonder reden, na herladen weer terug) — terwijl *"Lex
zag hier een Rechtssubject en ik vind van niet"* juist een interpretatiekeuze is die in het
spoor thuishoort; elders in de werkplek is zoiets wél een `reject` met reden of een `comment`. En
omdat dit lijstje de **restpost van de Critic** is, zegt structureel wegklikken iets over de kwaliteit
van de Critic: dat signaal hoort niet in een sessie-variabele te verdwijnen. Zolang `ontbrekend` bij
het chatbericht hoort en niet bij het annotatiedocument, is niets vastleggen eerlijker dan doen alsof.

### Symbolen zijn iconen, geen tekens

`components/ui/Icoon.tsx` levert de kleine iconen (chevron, waarschuwing, vinkje, ruit, cirkel) als
inline SVG op `1em` met `currentColor`. Gebruik die, en zet geen los teken in de UI: het font laadt
alleen de **latin-subset** van Fira Sans (`app/fonts.ts`), dus `▾ ◇ ▸ ⚠ ✓ ← ○` vallen terug op
`system-ui` — San Francisco op iOS, Roboto op Android, Segoe op Windows. Andere breedte, ander
gewicht, andere optische grootte, en dus een kaart die op een telefoon net wat anders oogt dan op
desktop. Emoji hebben dat probleem in het kwadraat: die worden door het besturingssysteem getekend,
in kleuren die niets met de huisstijl te maken hebben. `·` (U+00B7) mag wél: dat zit in de subset.

Eén uitzondering, en die is principieel: tekst die als **inhoud** wordt opgeslagen (de foutmelding
die als chatbericht de geschiedenis in gaat, `WerkplekClient`) kan geen component dragen. Daar staat
geen icoon maar een woord.

**De aandacht-as zegt wat hij bedoelt.** Het oordeel van de Critic staat op de reviewkaart als
**badge met tekst** — *Geen bezwaar* / *Even kijken* / *Waarschijnlijk fout* — in dezelfde vorm als de
documentstatus-badge (`AANDACHT_PILL` in `ReviewQueue.tsx` naast `DOCUMENT_STATUS_STYLE`): één
badgevorm in de hele app. Dat was een rondje van 8px met de betekenis alleen in een `aria-label`; wie
de kleurcode niet kende zag een stip en verder niets. Kleur blijft meedoen via de linker accentrand en
de zachte tint (dat is het scan-signaal in een lange lijst), maar draagt het oordeel niet meer alleen.
De badge-achtergrond staat op volle sterkte terwijl de kaart eronder dezelfde tint op 40% draagt —
zonder dat verschil verdwijnt hij in zijn eigen kleurfamilie.

**De kaartkop is mobiel gestapeld en op `sm:` één regel.** Links de korte, voorspelbare dingen
(aandacht-badge, lidnummer) mét de acties; de klassebadge daaronder over de volle breedte, en op een
breed scherm ertussen. Zonder die splitsing vocht een lange klassenaam ("Parameter en
parameterwaarde") met *Akkoord* en het kruisje om dezelfde regel. De klassenamen zijn canoniek, dus
korter maken mag niet — dan moet de ruimte mee. Zelfde patroon als `ui/ButtonRow`.

**Het lidnummer staat alleen op de kaart als het document méér dan één lid beslaat** (`toonLid` uit
`ArtefactInhoud`, afgeleid van `doc.lid`). Is het tot één lid afgebakend, dan zegt de kop het al
("Invorderingswet 1990 — artikel 9 lid 1") en herhaalde elke kaart dezelfde mededeling. Bewust
afgeleid van het document en niet van de elementen: anders verschijnt en verdwijnt het lidnummer
terwijl je reviewt.

**Kleur betekent iets, of hij hoort er niet.** De reviewkaart gebruikt kleur voor de aandacht-badge,
de JAS-badges en de accentrand — dingen die een oordeel dragen. De knoppen volgen de app: primair is
lintblauw (`bg-accent`, zoals `Button variant="primary"`), tweede keuze is een outline. *Akkoord* was
volvlak groen en *Naast me neerleggen* volvlak hemelblauw; dat zijn statuskleuren, en die schreeuwen
naast de gedempte tinten van een kaart.

### Toegankelijkheid (WCAG 2.2 AA, NLDS-niveau)

- Markeringen in de tekst zijn **`<mark role="button" tabIndex={0}>`** met een `onKeyDown` voor
  Enter/Space — focusbaar en met het toetsenbord te bedienen (2.1.1), maar wél **inline**. Een echte
  `<button>` is inline-block en dus atomair: liep de markering over twee regels, dan werd hij een
  rechthoekig blok tot aan de rechterrand en zakte de tekst erna (de afsluitende punt van het lid)
  naar de volgende regel. Daarbij hoort `box-decoration-clone`, anders krijgt alleen het eerste
  regelfragment een linkerrand en het laatste een rechter.
- **Klikdoelen ≥ 24×24 CSS-px** (2.5.8) via `min-h-[24px]` op chips/knoppen, met de bestaande
  `coarse:`-variant naar 44px op aanraakschermen (het AAA-niveau 2.5.5 dat NLDS aanhoudt).
- **Een uitklapper blijft binnen het scherm.** `components/ui/Popover` hangt met CSS aan zijn
  trigger (`positie`), en die weet niet waar hij op het scherm staat: een rechts uitgelijnd paneel
  bij een knop die zelf al rechts staat, steekt links buiten beeld — op een telefoon las de
  exportlijst zo met de eerste tekens eraf. Het component meet daarom na het openen en corrigeert
  horizontaal (`lib/popover.ts:klemHorizontaal`, pure functie, getest zonder DOM). Verticaal kiest
  de aanroeper zelf een richting (`top-full`/`bottom-full`) — dát is de as waar hij zicht op heeft.
  Wie een paneel de kolombreedte wil laten volgen gebruikt `positie="inset-x-3 …"` met
  `containerClassName="static"`, zoals de berichtenbel en het gebruikersmenu in de sidebar; dan kán
  het per definitie niet uitsteken. `SelectiePopover` staat los (hij hangt aan een muispositie, niet
  aan een element) en klemt zichzelf via `plaatsPopover`, inclusief zijn breedte op een smal scherm.
- Eén **`.focus-ring`-utility** in `globals.css` (2.4.13, AAA): dubbele ring zodat de focus ook op de
  donkere JAS-klassekleuren opvalt. Gebruik die in plaats van een eigen `focus-visible:outline`.
- Elke wijziging wordt **aangekondigd** via de `sr-only aria-live`-regio in `WerkplekClient`
  (`beslissingMelding`). Zonder dat gebeurt annoteren voor een schermlezer volledig stil.

### Reviewen zonder formulier

De reviewkaart kent geen modi meer (`Aanpassen` → veld → reden → `Opslaan`). Elk veld schrijft
zichzelf weg en de `review_reason` wordt **afgeleid** uit wát er veranderde — vragen wat je zojuist
deed is dubbelop. Die afleiding staat **server-side** (`api/app/routers/annotatie.py:
_reden_uit_diff`), niet meer hier: de api berekent de diff toch al, en een reden die hij niet kan
toetsen hoort niet in een auditspoor. De client stuurt bij een edit dus géén `review_reason` mee.
Bij **verwerpen** blijft de reden een vraag aan de jurist; die informatie staat in geen diff.

- **Klasse** = de badge zelf; klikken opent het palet, klikken op een klasse ís de wijziging.
- **Toelichting** is een inline veld (Enter/blur bewaart, Escape annuleert). Een gevulde toelichting
  leegmaken vraagt een tweede klik — dat doe je met één misklik en er is geen undo.
- **Bevestigen doet de knop zelf.** Onomkeerbare handelingen vragen overal in deze app een tweede
  klik op dezelfde plek (`components/ui/BevestigKnop.tsx`); er is geen `window.confirm` meer. Dat was
  een systeemvenster in systeemtaal midden in een app met een eigen vormtaal — niet te stylen, niet
  te testen, en in sommige contexten geblokkeerd. Scherp gezet ontwapent de knop vanzelf (4 s, blur
  of Escape): een knop die scherp blijft staan is een val, juist bij die handelingen.
- **× betekent weghalen**, met twee uitkomsten achter hetzelfde gebaar: een agent-voorstel klapt de
  redenen-chips uit (één klik = verworpen, terug te draaien met *Heropenen*), een eigen markering
  verandert in "Wissen?" en is na de tweede klik echt weg (`DELETE`).
- **Een oordeel vergrendelt de kaart.** Bij `human_approved`/`rejected` (`isVergrendeld`, een ánder
  begrip dan `isBeslist` — dát stuurt de filters en de telling) is de klasse-badge een badge in
  plaats van een knop, staat de toelichting als platte tekst, en zijn *Akkoord*, het kruisje, de
  alternatieven en de kanttekening-acties weg. Ervoor in de plaats staat **Heropenen**
  (`type: "heropen"`), dat het element terugzet in de review. Zonder die knop was een akkoord een
  doodlopende weg: de bediening lag stil en er was niets dat hem weer aanzette — terwijl de
  klasse-badge en de toelichting ondertussen stilzwijgend een `edit` wegschreven, dus een akkoord
  betekende in de praktijk niets. Een **opmerking** mag wél op een vergrendeld element (die wijzigt
  de annotatie niet); `edited` vergrendelt bewust niet, anders wringt er een heropening tussen het
  wijzigen van een klasse en het typen van de toelichting; en een **eigen markering** vergrendelt
  niet, want die is `human_approved` bij het aanmaken — anders staat je verse markering meteen op
  slot, wisknop en al.
- **Verworpen markeringen tellen niet als "inmiddels gemarkeerd"** (`alGemarkeerd` in
  `lib/annotatie.ts`, gebruikt door `OntbrekendLijst`). Verwerp je een markering, dan wil je het
  ontbrekend-item juist opnieuw kunnen toevoegen; het bleef er met een vinkje bij staan. Zelfde
  regel als in `DocumentPaneel`, dat verworpen markeringen ook niet meer oplicht.
- **De reden blijft alleen bij verwerpen een vraag**: die informatie heeft alleen de mens.
- **Fragment inkorten/uitbreiden**: klik de markering aan en selecteer opnieuw. Raakt de selectie het
  bereik van de actieve markering (`overlaptSelectie` + `vindPositie`, dezelfde functie als de
  weergave), dan biedt `SelectiePopover` bovenaan *Fragment aanpassen* aan — één klik, mét een nieuw
  anker. Geen overlap = gewoon een nieuwe markering. Bewust wél die klik: een selectie die je maakte
  om te lezen mag nooit stilzwijgend een annotatie wijzigen.
- **Geen lifecycle-jargon in beeld**: de kaart toont "voorstel van Lex" / "door jou
  aangepast" / "door jou gemarkeerd" + tijd. Het volledige spoor staat in het auditlog.

### De annotatie exporteren

Een knop *Exporteren* in de kop van het artefact (`components/workbench/ExportKnop.tsx`) biedt
**PDF / CSV / JSON**. Drie dingen om te kennen:

- **Ook halverwege.** Geen statusdrempel: een concept exporteren is een normale handeling, en het
  bestand zegt zelf hoeveel er nog te beoordelen is. Een drempel zou de jurist dwingen te doen
  alsof hij klaar is.
- **De wettekst reist mee.** De api heeft hem niet (de graaf is de bron), dus de knop stuurt
  `info.leden_teksten` mee in de body. Zonder leden laat het rapport dat blok weg — nooit een
  gereconstrueerde tekst naast een letterlijk citaat.
- **De bestandsnaam komt van de server** (`Content-Disposition`), zodat hij overal gelijk is. De
  BFF-route moet die header dus doorgeven (`app/api/_lib/proxy.ts` → `PASS_THROUGH_HEADERS`) en de
  queryparam `formaat` expliciet doorsturen; een proxyroute die dat laat vallen faalt stil op het
  default-formaat. Downloaden zelf gaat via `exporteerDocument` in `lib/api.ts` (Blob →
  `createObjectURL` → `<a download>`) — het enige downloadpatroon in deze app.

Wat de export draagt (en waarom het er is): naast de tabel het **volledige spoor** per markering
en **met welk model** de agent het voorstel maakte (`AgentRun`, zie hieronder). Zonder dat laatste
is een export achteraf niet te verantwoorden.

### Herkomst van een agent-ronde

graph-qa stuurt per annotatiebeurt één `run`-SSE-event vóór de elementen; `WerkplekClient` houdt
het vast en geeft het mee aan `zetElementen`, die het als `run` in de PUT zet. De api hangt het aan
het document (`runs[]`) én aan elk element (`geproduceerd_door`). Stuur je het niet mee, dan blijft
het bestaande spoor staan — nooit overschrijven met "onbekend".

### Zelf annoteren (tekstselectie)

De jurist kan in `DocumentPaneel` tekst selecteren en die zelf markeren. Zes dingen om te kennen:

- **Een selectie eindigt niet altijd met een muisklik.** Naast `onMouseUp` luistert
  `DocumentPaneel` op documentniveau naar `keyup` (Shift-gebaren) en `touchend`: met Shift+pijltjes
  komt er geen muisevent langs — dan is zelf markeren met het toetsenbord onmogelijk (WCAG 2.1.1) —
  en het verslepen van een selectiegreep op een aanraakscherm laat er ook geen achter. Het paneel
  ruimt de DOM-selectie op als het de popover sluit (`sluitSelectie`), anders klapt die bij de
  volgende tik meteen weer open.
- **De rekenkern staat in `lib/selectie.ts`**, niet in het component: vitest draait node-env zonder
  DOM, dus alleen zo is die logica te testen. Het component doet enkel de `TreeWalker`-wandeling en
  geeft knooplengtes door aan `offsetUit`. Dat werkt doordat de alinea één aaneengesloten reeks
  `span`/`mark` is waarvan de tekstknopen samen exact de bron vormen.
- **De brontekst is een lijst `LidRegel`, geen lijst strings** (`regelsVan`/`bronVan` in
  `lib/annotatie.ts`). Het lidnummer reist naast de regel mee omdat het **niet uit de volgorde is af
  te leiden**: bij een op één lid afgebakend document levert de graaf alléén dat lid — index 0, lid 3 —
  en ingevoegde leden heten 2a. `lidUitOffset` gaf eerder `String(i + 1)` terug en legde een eigen
  markering dus op het verkeerde lid vast, tot in het anker en het auditspoor.
- **De context bij een annotatiebeurt is één document.** `eigenMarkeringenVoorContext(doc)` levert de
  eigen, niet-verworpen markeringen van de bepaling die openstaat — niet alles wat er in het gesprek
  is geopend. Anders legt de Critic een fragment uit artikel 36 naast de tekst van artikel 8.
  graph-qa handhaaft diezelfde grens nog eens tegen het corpus dat het zelf ophaalde.
- **Elk element draagt een `anker`**: exacte offsets + quote-met-context + een hash van de bron.
  `segmenteer` gebruikt die in drie stappen (offsets → context → eerste voorkomen), waardoor twee
  identieke fragmenten in één artikel uit elkaar blijven en een markering een herimport overleeft. `vindplaats` blijft de mensleesbare bronaanduiding; daar horen geen offsets in.
- **De tekst toont hoogstens ÉÉN markering: de geselecteerde.** Alles tegelijk kleuren was
  onleesbaar én onvolledig — twee markeringen kunnen niet op dezelfde tekst liggen, dus wat binnen
  een langere markering viel (een Rechtsobject in een zin die als geheel een Afleidingsregel is)
  verdween uit beeld. De reviewlijst is de ingang; de tekst laat zien wáár het gekozen element
  staat. Nog eens klikken verbergt hem weer, en een eigen verse markering wordt meteen actief.
  Daarmee is er ook geen overlap-prioritering meer nodig in `segmenteer`; de bevriezingsregel
  (mens wint) leeft server-side.

Eigen markeringen gaan via `POST .../elementen` (niet de PUT: dat is de uitkomst van een
agent-ronde) en zijn meteen `human_approved`. Verwijderen kan alleen bij je eigen markeringen; een
agent-voorstel verwérp je, zodat het auditspoor laat zien dát er een voorstel was.

## Observability

`instrumentation.ts` registreert OpenTelemetry via `@vercel/otel` (gated op
`OTEL_EXPORTER_OTLP_ENDPOINT`; auto-tracing van route handlers + uitgaande `fetch` met
traceparent-propagatie → end-to-end trace over de keten frontend → API/graph-qa). `lib/logger.ts` is de
**server-only** gestructureerde JSON-logger (mirror van de MCP-logger: secret-redactie, `LOG_LEVEL`,
`trace_id`/`span_id`), ingezet in de BFF-lagen (`app/api/_lib/proxy.ts`, `lib/server.ts`, de
annotatie-agent-route). Nooit
importeren vanuit een Client Component (net als `lib/config.ts`/`lib/server.ts`), en nooit
tokens/secrets/inhoud loggen. In de vitest-node-omgeving wordt `server-only` gestubd
(`vitest.config.ts` → `test/stub-empty.ts`). Zie `docs/observability.md`.

## Regels (niet aan tornen)

- **Token nooit naar de client.** Geen import van `lib/config.ts`/`lib/server.ts` in Client
  Components; geen token in `NEXT_PUBLIC_*`. Nieuwe upstream-calls lopen via een Route Handler.
- **Geen onbetrouwde waarde rechtstreeks in een `href`.** Velden uit de analyse-pipeline/LLM
  (`bronreferentie`, `verwijzing.doel.target`) kunnen een `javascript:`/`data:`-scheme bevatten —
  React escaped tekst, maar niet de href-scheme. Route ze altijd via **`bronHref`** in `lib/url.ts` —
  één functie voor alle vormen die de agent levert (jci, graaf-IRI `urn:bwb:…`, kaal
  BWB-id, complete wetten.overheid.nl-URL); onbekend of onbetrouwbaar → `undefined` ⇒ platte tekst.
  Er stonden twee bijna gelijknamige helpers en de bronnenlijst greep de verkeerde: die plakte een
  graaf-IRI achter `wetten.overheid.nl/` en kwam door de hostcontrole heen, dus stond er een
  klikbare link naar een 404 onder elk antwoord.
- **Status/headers ongewijzigd doorgeven.** De API bezit het gedrag (409 bij verkeerde state, 429 +
  `Retry-After`, 404 op andermans id). De BFF maskeert dat niet; de UI reageert erop.
- **Admin-pad apart.** `/api/admin/*` → `proxy(..., { admin: true })` → `/v1/admin/*`. Het admin-token
  zit server-side in de BFF. Meng de twee tokens niet.
- **Login = Auth.js (NextAuth v5), API is identiteitsbron.** De hele app zit achter een login met
  **userid** + wachtwoord (`auth.ts` + `auth.config.ts`; `proxy.ts` — de Next 16-opvolger van
  de `middleware`-conventie — bewaakt élke route en
  stuurt niet-ingelogden naar `/login`). De **matcher** verankert de bestandsextensies op het einde
  en zondert `/api/` uit van die tak: zonder dat viel elk pad met ".png" eríń (`/api/gesprekken/abc.png`)
  buiten de gate, en een route-parameter mag er nu eenmaal uitzien als een bestandsnaam.
  `proxy.test.ts` leest het patroon uit de bron en legt dat vast — houd de matcher daarom een
  **letterlijke string**, want Next analyseert hem statisch bij het bouwen. Inloggen gaat uitsluitend met de userid; e-mail wordt bij
  het aanmaken verplicht/uniek geregistreerd maar is geen inlog-identiteit. De sessie is een
  httpOnly JWT-cookie (`AUTH_SECRET`) die de `userid` + rol draagt; de Credentials-provider
  verifieert server→server bij de API (`lib/server.ts → verifyCredentials` → `/v1/auth/verify`). De
  **API blijft de identiteitsbron** (users-tabel met `userid` als sleutel, wachtwoord-hash, TOTP);
  de BFF houdt alleen de sessie. Rollen: **`beheerder`** (mag `/beheer` + `/api/admin/*`) en
  **`analist`** (de rest) — afgedwongen in de `authorized`-callback (edge) én server-side in
  `app/instellingen/[[...tab]]/page.tsx` (`isAdminTab(actief) && !isBeheerder` → redirect). De eerste keer (lege users-tabel) maakt `/setup` eenmalig de eerste
  beheerder; daarna sluit die route. **Gebruikersbeheer** zit in de beheertab (`UsersPanel`, achter het
  admin-token). **2FA (TOTP)** is optioneel en self-service in de accounttab; verdere gebruikers maakt
  een beheerder aan met een eenmalig tijdelijk wachtwoord. De account/2fa-BFF-routes zetten de
  ingelogde identiteit als vertrouwde `X-User-Id`-header (uit de sessie, nooit uit browser-input).
  Let op: Auth.js' eigen routes leven onder `/api/auth/*` — daar geen eigen BFF-route bijzetten
  (de eenmalige-registratie-proxy staat daarom op `/api/setup`).
- **Sessie-revocatie + CSRF defense-in-depth.** De sessie is rollend met een **per-login duur**:
  `session.maxAge` = 30 dagen (`SESSIE_LANG`, de cookie-/bovengrens) + `updateAge` = 1 dag in
  `auth.config.ts`, maar de custom `jwt.encode` in `auth.ts` zet de effectieve JWT-`exp` op
  **30 dagen als "Ingelogd blijven op dit apparaat" is gekozen** (`token.rememberMe`), anders
  **12 uur** (`SESSIE_KORT`). Die keuze is één checkbox op `/login` (default uit), die óók de
  trusted-device-cookie stuurt (2FA overslaan) — op het 2FA-scherm is er dus geen aparte checkbox
  meer; de keuze reist via `sessionStorage` (`wa_login_remember`) mee naar `/login/2fa`. De
  node-`jwt`-callback in `auth.ts` herverifieert elke ~5 min de accountstatus bij de API
  (`lib/server.ts → getAccountStatus` → `/v1/auth/me`): een gedeactiveerd account invalideert de
  sessie, een rolwijziging werkt direct door in het token. De edge-middleware draait de lichte
  `jwt`-variant zonder herverificatie (`lib/server.ts` is node-only) — elke `auth()`-aanroep in
  Server Components/route handlers loopt wél langs de herverifiërende versie, en de ~5-min
  herverificatie (niet de lange `maxAge`) is de feitelijke revocatie-grens. Daarnaast
  handhaaft de `authorized`-callback een **Origin-check** op muterende BFF-calls
  (`POST/PUT/PATCH/DELETE` op `/api/*`, incl. de publieke `/api/login-verify`): een meegestuurde
  vreemde Origin → 403; zonder Origin-header valt het terug op `SameSite=Lax`. De cookie-flags
  (`httpOnly`/`sameSite=lax`/`secure`) staan expliciet in `authConfig` vastgelegd.
- **Geen keuzemenu's — het is chat op de graaf.** De werkplek kiest geen wet uit een lijst: je stelt
  je vraag/annotatie-opdracht en de agent vindt de bepaling in de graaf (het `doel`-event levert
  `bwbId`/`artikel`/`citeertitel`). Er is dus geen wet-dropdown of wet-catalogus meer.
- **Huisstijl via tokens, niet hardcoded.** Kleur en typografie lopen via de tokens in
  `app/globals.css` + `tailwind.config.ts` (en `lib/jas.ts` voor de JAS-badges) — strooi
  geen losse hex-waarden door componenten. Het officiële logo-asset (`public/belastingdienst-logo.svg`)
  blijft ongewijzigd; de JAS-klassekleuren komen exact uit `docs/wetsanalyse/wa-table.png`.

## Commando's

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000 (draait API óók op 3000? → npm run dev -- -p 3001)
npm run build        # productiebuild (output: 'standalone')
npm run lint         # ESLint
npm run typecheck    # tsc --noEmit
npm test             # vitest (node-env, geen DOM — zie §Lagen)
```

Vereist een draaiende API (lokaal of het publieke domein) + de env-vars uit `.env.local`
(`API_BASE_URL`, `API_TOKEN`, `ADMIN_API_TOKEN`; zie README).

**Vóór een commit: `npm test && npm run lint && npm run typecheck`.** De testsuite hoort daarbij —
de rekenkern van deze app staat bewust in `lib/` juist zódat hij getest kan worden, en die tests
overslaan maakt die keuze zinloos.

<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->
