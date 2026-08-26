---
name: regelspraak
description: >-
  Formaliseert geduide Nederlandse wet- en regelgeving naar een uitvoerbare specificatie in
  RegelSpraak (de gecontroleerde natuurlijke taal van de Belastingdienst/ALEF) met daaronder
  GegevensSpraak (het objectmodel): objecttypen, attributen, kenmerken, domeinen, parameters,
  feittypen/rollen, en RegelSpraak-regels (resultaatdeel, voorwaardendeel, regelversies). Het
  resultaat is een traceerbaar model.json (via een HTML-viewer; .rs/Markdown als export).
  Gebruik deze skill zodra de gebruiker wet- of regelgeving wil omzetten, formaliseren of
  specificeren naar RegelSpraak of GegevensSpraak — ook bij vragen als "zet deze wetsanalyse
  om naar RegelSpraak", "maak een objectmodel/GegevensSpraak bij artikel X", "schrijf
  RegelSpraak-regels voor deze bepaling", "formaliseer dit naar uitvoerbare regels", "maak een
  ALEF-/Belastingdienst-regelspecificatie", of wanneer een geduide bepaling
  machine-uitvoerbaar moet worden vastgelegd. Volgt logisch op de wetsanalyse-skill (begrippen
  + afleidingsregels → GegevensSpraak + RegelSpraak), maar werkt ook zelfstandig vanaf
  wettekst (haalt die op via de wettenbank-MCP). Trigger ook bij twijfel: dit is de aangewezen
  werkwijze om de betekenis van wetgeving formeel en uitvoerbaar te specificeren.
---

# RegelSpraak (GegevensSpraak + RegelSpraak-regels)

## Wat dit is en waarom het zo werkt

Deze skill zet geduide wetgeving om naar een **formele, uitvoerbare specificatie** volgens de
**RegelSpraak-specificatie v2.3.0** van de Belastingdienst (de taal achter ALEF — *Agile Law
Execution Factory*). Het is de volgende stap in **Wendbare Wetsuitvoering**: na het duiden
(skill `wetsanalyse`: markeren/classificeren in JAS + begrippen en afleidingsregels) maak je
de betekenis machine-uitvoerbaar, terwijl ze leesbaar, testbaar en herleidbaar blijft.

De specificatie kent twee samenhangende talen:

- **GegevensSpraak — het objectmodel.** Welke *gegevens* bestaan er: **objecttypen** met hun
  **attributen** (en datatypes), **kenmerken**, **domeinen**, **parameters**, **feittypen +
  rollen** (relaties), eenheidssystemen, dimensies, tijdlijnen en dagsoorten. RegelSpraak
  *gebruikt* deze gegevens; je moet ze dus eerst specificeren.
- **RegelSpraak — de regels.** Per regel een **resultaatdeel** (de actie: een waarde berekenen,
  een kenmerk toekennen, een controle…), optioneel een **voorwaardendeel** (`indien…`) en een
  **variabelendeel** (`Daarbij geldt:`), binnen één of meer **regelversies** met een
  geldigheidsperiode.

Het resultaat is één traceerbaar **`model.json`** (de primaire bron), gepresenteerd via een
HTML-viewer; de letterlijke **RegelSpraak-tekst** (`.rs`/Markdown) is als export beschikbaar.

Na het opstellen van GegevensSpraak (stap 2) en van de RegelSpraak-regels (stap 3) pauzeert de
skill voor een **review-checkpoint**: de analist valideert het tussenresultaat in een lokale
reviewpagina en geeft feedback, die je verwerkt voordat je verdergaat (zie stap 2b, 3b en
`references/review-checkpoints.md`).

**Dit is een hulpmiddel, geen vervanger van de regelanalist.** De methode draait om het
*expliciet en uitlegbaar* maken van de formalisering, zodat juristen, informatieanalisten en
ICT-ontwikkelaars er samen over kunnen beslissen. Lever een onderbouwd concept op: formaliseer
wat helder is, en markeer interpretatiekeuzes, aannames en open normen als zodanig
(`twijfel`/`validatiepunten`) in plaats van schijnzekerheid te produceren.

## Brongetrouwheid is niet onderhandelbaar

In een uitvoeringscontext (zoals de Belastingdienst) moet de specificatie kloppen met zowel de
wet als de taal. Daarom:

- **Gebruik uitsluitend echte RegelSpraak v2.3.0-taalpatronen.** Verzin nooit syntax,
  sleutelwoorden of operatoren. Twijfel je over een taalpatroon, raadpleeg dan de references
  (`gegevensspraak-referentie.md`, `regels-en-resultaat-referentie.md`,
  `expressies-en-operatoren-referentie.md`) — die zijn de letterlijke samenvatting van de spec.
  Wat daar niet in staat, schrijf je niet: noteer het als validatiepunt.
- **Houd alles herleidbaar.** Elk objecttype/attribuut/kenmerk/parameter/feittype en elke
  regel draagt een **`herkomst`** naar het bron-begrip of de bron-regel uit de wetsanalyse
  (en daarmee naar artikel + lid), of — in het standalone-pad — naar de letterlijke wettekst.
- **Citeer de termen uit de bron.** De `naam` van een objecttype/attribuut/begrip is de
  **voorkeursterm** van het bijbehorende wetsanalyse-begrip; verzin geen nieuwe termen.
- **Forceer niets.** Past een afleidingsregel niet zuiver op één resultaatactie, kies dan de
  best passende, leg de keuze vast in `twijfel`, en neem het op bij de validatiepunten.

## Stap 1 — Bepaal de basis

De skill werkt **flexibel** vanuit twee soorten input. Bepaal eerst welke je hebt:

1. **Vanuit een wetsanalyse-`rapport.json` (voorkeur).** Is er een afgeronde wetsanalyse voor
   dit werkgebied (`analyses/<werkgebied>/rapport.json`), gebruik die dan als basis. Lees het
   rapport **deterministisch** in met het handoff-script (overtypen is foutgevoelig en laat
   herkomst-id's verschuiven):

   ```bash
   python "<skill>/scripts/ingest_rapport.py" \
     --rapport analyses/<werkgebied>/rapport.json \
     --out     regelspraak/werk/ingest.json
   ```

   Het script schrijft één `ingest.json` met het `werkgebied`, de **bronnen** (lichte index met
   `leden`, `verwijzingen` en `Brondefinitie`-markeringen), de **begrippen** (activiteit 3a) en de
   **afleidingsregels** (activiteit 3b) — met behoud van de oorspronkelijke id's (`b*`, `r*`, `v*`).
   De begrippen voeden GegevensSpraak; de afleidingsregels en hun voorwaarden voeden de
   RegelSpraak-regels; de brondefinities/verwijzingen voeden domeinen en herleidbaarheid. Werk
   verder vanuit `ingest.json`; lees `references/vertaalpatronen.md` voor hoe je per onderdeel
   vertaalt. Meldt het script dangling referenties, signaleer dat dan als validatiepunt.
2. **Standalone vanuit wettekst.** Is er geen rapport, haal dan de actuele wettekst zelf op via
   de wettenbank-MCP (`wettenbank_zoek` → `wettenbank_structuur` → `wettenbank_artikel`, en
   `wettenbank_zoekterm` voor definitieartikelen) en doe een **lichte** identificatie van de
   gegevens en regels. **Advies:** stel de gebruiker voor om eerst de `wetsanalyse`-skill te
   draaien — een goede JAS-duiding maakt de formalisering aanmerkelijk betrouwbaarder. Het
   standalone-pad staat beschreven in `references/vertaalpatronen.md`.

Bepaal en leg het **werkgebied** vast (naam + afbakening, `werkgebied.scoping`). De afbakening is
een **harde gate, geen formaliteit**: noteer concreet wat je **wél** en wat je **niet**
formaliseert, met reden — met name de delen die RegelSpraak v2.3.0 niet native kan uitdrukken (bv.
een iteratieve termijnberekening of een schakelbepaling) horen hier expliciet *buiten scope* te
worden gezet en bij de validatiepunten te landen. Zonder een concrete afbakening ga je **niet**
door naar stap 2: een lege of generieke `scoping` (zoals een herhaling van de werkgebied-naam) is
een stopconditie, omdat de skill anders alles probeert te formaliseren en bij een taalgrens gaat
improviseren. **De regelspraak-`scoping` is een ánder concept dan de wetsanalyse-`scoping`:** de
eerste bakent het *duiden* af (welke bronnen/leden zijn geanalyseerd), de tweede het *formaliseren*
(wat wordt wél/niet uitvoerbaar gemaakt, met de RegelSpraak-grenzen). Het **verbatim overnemen** van
de analyse-scoping uit het rapport telt daarom **niet** als formaliseer-afbakening en is óók een
stopconditie — formuleer een eigen afbakening die de niet-formaliseerbare delen expliciet benoemt. Schrijf alle output naar één analysemap: `analyses/<werkgebied-slug>/regelspraak/`.
Bestaat er al een wetsanalyse-map voor dit werkgebied, gebruik die map (een `regelspraak/`-submap
ernaast).

Is de MCP niet beschikbaar én is er geen rapport, zeg dat eerlijk en werk verder met door de
gebruiker aangeleverde tekst, met dezelfde brongetrouwheid.

## Stap 2 — GegevensSpraak: het objectmodel opstellen

Bouw eerst het objectmodel; de regels (stap 3) hebben het nodig. Lees
`references/gegevensspraak-referentie.md` voor de exacte syntax van elk onderdeel en
`references/vertaalpatronen.md` voor de JAS-klasse → GegevensSpraak-afbeelding. **Werkset-
discipline:** laad de `references/` één keer aan het begin van de fase en herhaal ze niet per
revisieronde; lees een afgeronde `werk/.../model.json` niet onnodig volledig opnieuw in maar
werk gericht met de id's/herkomst. Bij een groot objectmodel of veel begrippen blijft de
context zo binnen de perken. In het kort, in deze volgorde:

1. **Eenheidssystemen en domeinen** die je hergebruikt (bv. `Bedrag` = Numeriek met 2
   decimalen, eenheid €; een enumeratie voor een limitatieve opsomming). Domeinen geven een
   vaak voorkomende waardesoort één eenduidige plek.
2. **Objecttypen** uit de **rechtssubjecten** en **rechtsobjecten** (`Objecttype de <naamwoord>
   (mv: …) (bezield)`). Markeer levende wezens als `(bezield)`.
3. **Attributen** per objecttype uit de **variabelen**, elk met een **datatype** (Numeriek,
   Tekst, Boolean, Datum-tijd, Percentage) of een domein, en zo nodig een eenheid, dimensie of
   tijdlijn.
4. **Kenmerken** uit booleaanse/ja-nee-eigenschappen (`is …` bijvoeglijk, `heeft …`
   bezittelijk, of overig). Gebruik bij voorkeur een kenmerk in plaats van een Boolean-attribuut.
5. **Parameters** uit de **parameters/parameterwaarden** (constanten die voor iedereen gelden,
   bv. een tarief of drempel) — zo staan vaste waarden niet "hard" in de regels.
6. **Feittypen + rollen** uit de **rechtsbetrekkingen** en andere relaties tussen objecttypen
   (enkelvoudige/meervoudige rollen; wederkerig waar beide kanten dezelfde rol spelen).
7. Waar de wet erom vraagt: **dimensies** (meerdere waarden per attribuut, bv. per jaar),
   **tijdlijnen** (waarden die in de tijd wijzigen) en **dagsoorten** (feestdagen e.d.).

Geef elk objecttype een stabiel `id` en een `herkomst` naar het bron-begrip (`begrip_ids` +
`vindplaatsen`). Verzin geen objecttypen/attributen die niet uit de bron volgen.

## Stap 2b — Review-checkpoint na GegevensSpraak

Het objectmodel is de fundering; laat het door de analist valideren vóór je regels schrijft.
Dit is een **iteratieve lus** tot de analist akkoord is zonder opmerkingen. Lees
`references/review-checkpoints.md` voor het datacontract; in het kort, met `N` = rondenummer
(start op 1), relatief aan de analysemap:

1. Schrijf het tussenresultaat naar `regelspraak/werk/gegevensspraak/ronde-{N}/model.json`:
   het `werkgebied`-object + het `gegevensspraak`-object (objecttypen, domeinen, parameters,
   feittypen, …) met **stabiele id's**. Overschrijf eerdere rondes niet.
1b. Voer de pre-check uit:
   `python "<skill>/scripts/validate_regelspraak.py" --input regelspraak/werk/gegevensspraak/ronde-{N}/model.json --stap gegevensspraak`
   - Werk je vanuit een rapport? Voeg dan `--ingest regelspraak/werk/ingest.json` toe: dat toetst
     de **herkomst-integriteit** (een `begrip_id`/`bron_id` dat niet in de wetsanalyse bestaat →
     blokkerende fout) en de **dekking** (een ingest-begrip dat door geen declaratie wordt geraakt
     → waarschuwing: dek het, of zet het bewust buiten scope bij de validatiepunten). Standalone
     (zonder rapport): laat de flag weg.
   - Exit 2 (fouten): herstel vóórdat je de server start.
     Bij `REGELSPRAAK_NO_REVIEW=1`: log de fouten maar blokkeer niet — ga door.
   - Exit 1 (waarschuwingen): ga door; toon ze als context bij de review.
   - Exit 0: ga direct door.
2. Start de review-server in de achtergrond. Ronde 1:
   `python "<skill>/scripts/review_server.py" --input regelspraak/werk/gegevensspraak/ronde-1/model.json --stap gegevensspraak --feedback-out regelspraak/werk/gegevensspraak/ronde-1/feedback.json --ronde 1`
   Ronde 2+: voeg `--ronde {N}` en `--vorige regelspraak/werk/gegevensspraak/ronde-{N-1}` toe.
3. Geef de analist de URL (`http://localhost:3120`) en **rond je beurt af**: vraag de analist
   de review te bekijken, per item of in het algemeen desgewenst feedback te geven, en op de
   **verstuurknop** te klikken (zonder feedback telt dat als akkoord). Ga niet zelf verder.
4. Zodra de analist bevestigt: lees `regelspraak/werk/gegevensspraak/ronde-{N}/feedback.json`.
   - Bij `akkoord` **zonder** items en **zonder** algemene feedback: stop de server — ga door
     naar stap 3.
   - Anders: verwerk **elke** correctie (objecttype/attribuut/kenmerk/parameter/feittype
     toevoegen, wijzigen, verwijderen; datatype/domein bijstellen), stop de server, verhoog
     `N` en ga terug naar stap 1. Noteer per ronde wat je wijzigde voor de reviewlog.
5. **Veiligheidscap:** stop na maximaal 6 rondes; meld dit en neem resterende punten op bij de
   validatiepunten.

Sla deze lus alleen over als `REGELSPRAAK_NO_REVIEW=1` in de omgeving staat (alleen voor
geautomatiseerde evals): schrijf dan één keer `ronde-1/model.json` en noteer dat de reviews
zijn overgeslagen.

## Stap 3 — RegelSpraak: de regels opstellen

Lees `references/regels-en-resultaat-referentie.md` (regelstructuur + de acht resultaatacties +
voorwaarden/variabelendeel) en `references/expressies-en-operatoren-referentie.md` (expressies,
operatoren, predicaten) voordat je regels schrijft. In het kort:

Maak **per afleidingsregel** (en per voorwaarde-set) een `Regel`. Een regel heeft:

- een **naam** (`Regel <naam>`), uniek en sprekend;
- één of meer **regelversies** met een geldigheidsperiode (`geldig altijd`, of
  `geldig vanaf <datum> t/m <datum>`); verschillende versies mogen niet overlappen;
- een **resultaatdeel** (verplicht) — kies de juiste van de **acht acties**:
  - **Gelijkstelling** voor een rekenregel (`De <attribuut> van een <onderwerp> moet berekend
    worden als <expressie>`) of een directe toekenning (`… moet gesteld worden op <waarde>`);
  - **Kenmerktoekenning** voor een beslis-/specialisatieregel
    (`Een <objecttype> is/heeft een <kenmerk>`);
  - **Consistentieregel** voor een controle (`… moet voldoen aan …` / `moet ongelijk zijn aan
    …`); **Initialisatie**; **ObjectCreatie**; **FeitCreatie**; **Verdeling**;
    **Dagsoortdefinitie**; **Startpuntbepaling** — zie de referentie voor het taalpatroon;
- optioneel een **voorwaardendeel** (`indien …`, een enkele of samengestelde conditie met
  bullets `•` en een kwantificatie als `alle`/`geen van de`/`ten minste <n>`), afgesloten met
  een punt;
- optioneel een **variabelendeel** (`Daarbij geldt:` met lokale variabelen).

Gebruik in expressies alleen de bestaande **operatoren** (`plus`, `min`, `verminderd met`,
`maal`, `gedeeld door`, `de som van`, `het aantal`, `de maximale waarde van`, …) en
**predicaten** (`is gelijk aan`, `is groter dan`, `is leeg`, `voldoet aan de elfproef`, …)
zoals in `expressies-en-operatoren-referentie.md`. Verzin er geen.

Schrijf elke regel als letterlijke RegelSpraak in het veld `regelspraak_tekst` en geef de regel
een `herkomst` naar de bron-afleidingsregel (`regel_id` + `vindplaatsen`). Markeer
interpretatiekeuzes in `twijfel`.

**Terugkoppeling naar stap 2 — het objectmodel is niet onomkeerbaar bevroren.** Blijkt bij het
schrijven van een regel dat het objectmodel een attribuut, parameter of feittype mist (bv. een
`toepasselijke invorderingstermijn` of een `vervaldatum` om een termijn in te berekenen), keer dan
terug naar **stap 2** en breid het model uit in een nieuwe GegevensSpraak-ronde. Misbruik **niet**
een bestaand attribuut als opslagplek (een berekende maandentelling hoort niet in een jaartal-veld)
en schuif het tekort **niet** weg naar de validatiepunten alsof het onoplosbaar is. Het
checkpoint 2b bevriest het model alleen tussen rondes door, niet definitief: een ontbrekend gegeven
ontdekt in stap 3 is een legitieme reden om stap 2 te heropenen. Raadpleeg bij twijfel over het
juiste modelpatroon `references/vertaalpatronen.md` §5 (booleaan vs datum/duur, rolcheck vs
lege-waarde, enumeratie vs parallelle kenmerken, de iteratiegrens).

## Stap 3b — Review-checkpoint na de regels

Net als na stap 2: laat de regels door de analist valideren als dezelfde **iteratieve lus**,
tot akkoord zonder opmerkingen (zie `references/review-checkpoints.md`). Met `N` = rondenummer:

1. Schrijf `regelspraak/werk/regels/ronde-{N}/model.json`: het `werkgebied`-object, een lichte
   `gegevensspraak`-index (zodat de regels leesbaar zijn) en de `regels`-array (met **stabiele
   id's** en `regelspraak_tekst`) + concept-validatiepunten. Overschrijf eerdere rondes niet.
1b. Pre-check: `python "<skill>/scripts/validate_regelspraak.py" --input regelspraak/werk/regels/ronde-{N}/model.json --stap regels` (exit-gedrag als bij stap 2b). Vanuit een rapport: voeg `--ingest regelspraak/werk/ingest.json` toe — hier toetst het de herkomst-integriteit (`regel_id`/`bron_id`) en de dekking van de **afleidingsregels** (een ongedekte regel → waarschuwing).
2. Start de server met `--stap regels --feedback-out regelspraak/werk/regels/ronde-{N}/feedback.json --ronde {N}`; vanaf ronde 2 ook `--vorige regelspraak/werk/regels/ronde-{N-1}`.
3. Geef de URL (`http://localhost:3120`), **pauzeer**, en wacht op bevestiging van de analist.
4. Lees `regelspraak/werk/regels/ronde-{N}/feedback.json`. Bij `akkoord` zonder items en zonder
   algemene feedback: stop de server, de lus is klaar. Anders: verwerk de feedback, stop de
   server, verhoog `N` en herhaal vanaf stap 1. Noteer de wijzigingen per ronde. Cap: 6 rondes.

Dezelfde `REGELSPRAAK_NO_REVIEW=1`-uitzondering geldt (één keer `ronde-1/model.json`, lus
overslaan).

## Stap 4 — Model bouwen en presenteren

Het eindresultaat is één `model.json` (primaire bron), getoond via een HTML-viewer, met de
RegelSpraak-tekst als `.rs`/Markdown-export. Type niets over uit de ronde-bestanden.

**Stap 4a — Bouw model.json**

```bash
python "<skill>/scripts/build_regelspraak.py" \
  --werk regelspraak/werk \
  --out  regelspraak/model.json
```

Het script kiest per stap de hoogste ronde en combineert GegevensSpraak + regels tot één
`model.json`. De vrije tekstvelden (reviewlog GegevensSpraak, reviewlog regels, validatiepunten)
zijn nog leeg; het script meldt hoeveel er ontbreken.

**Stap 4b — Genereer de vrije tekstvelden** op basis van de feedback.json's en de
validatiepunten: de twee reviewlogs (wat per ronde gewijzigd is; bij 1 ronde direct akkoord:
`"1 ronde — direct akkoord, geen wijzigingen."`) en de **aandachtspunten voor validatie**
(interpretatiekeuzes, open normen, niet-formaliseerbare delen, aannames, wat buiten scope valt).

**Stap 4c — Voeg ze in** via dezelfde flags (`--reviewlog-gegevensspraak`, `--reviewlog-regels`,
`--validatiepunten`).

**Stap 4d — Start de viewer**

```bash
python "<skill>/scripts/rapport_server.py" --input regelspraak/model.json
```

Voeg `--no-browser` toe als `REGELSPRAAK_NO_REVIEW=1` in de omgeving staat. Geef de analist de
URL (`http://localhost:3121`) en **pauzeer**: vraag de analist het model te bekijken, eventueel
de §-velden bij te stellen, op **Opslaan** te klikken, en de RegelSpraak-tekst te downloaden via
**Schrijf .rs/Markdown**. Ga niet zelf door tot de analist bevestigt.

## Kwaliteitscheck voordat je oplevert

- Gebruikt elke declaratie en regel **alleen bestaande RegelSpraak v2.3.0-taalpatronen** (geen
  verzonnen syntax/operatoren/predicaten)?
- Heeft elk objecttype/attribuut/kenmerk/parameter/feittype en elke regel een `herkomst` naar
  het bron-begrip/de bron-regel (en daarmee naar artikel + lid)?
- **Wijst elke `herkomst` naar een bestaand ingest-id, en is elk ingest-begrip/-afleidingsregel
  gedekt of bewust buiten scope gezet?** Bij het rapport-pad borgt `validate_regelspraak.py --ingest`
  dit mechanisch (dangling herkomst = fout, ongedekte ingest = waarschuwing) — laat geen
  dangling- of dekkingsmelding onbeantwoord.
- Bestaat elk objecttype/elke rol/parameter waarnaar een regel verwijst ook echt in de
  GegevensSpraak (geen verwijzing naar niet-gedeclareerde gegevens)?
- Is het juiste **resultaatdeel** per regel gekozen (rekenregel → gelijkstelling-berekening,
  beslisregel → kenmerktoekenning/consistentieregel)?
- Zijn parameters (vaste waarden) en attributen (per geval verschillend) uit elkaar gehouden?
- **Wordt elke gedeclareerde parameter ook door een regel gebruikt?** De validator waarschuwt op
  ongebruikte parameters/objecttypen; ontbreekt het gebruik, dan mist er een regel (voeg hem toe)
  of is de declaratie overbodig (haal hem weg) — laat het niet als wees-declaratie staan.
- Zijn interpretatiekeuzes, open normen en niet-formaliseerbare delen expliciet benoemd in
  `twijfel`/`validatiepunten` in plaats van weggepoetst?
- Zijn beide review-checkpoints doorlopen tot akkoord (of bewust overgeslagen via
  `REGELSPRAAK_NO_REVIEW`), en is de feedback per ronde verwerkt en in de reviewlogs vastgelegd?

## Referentiedocumentatie

- `references/gegevensspraak-referentie.md` — de volledige GegevensSpraak-syntax (objecttypen,
  attributen, datatypes, domeinen, kenmerken, dimensies, eenheden, tijdlijnen, parameters,
  feittypen/rollen, dagsoort).
- `references/regels-en-resultaat-referentie.md` — de regelstructuur (regel, regelversie,
  basispatroon) en de acht resultaatacties + voorwaardendeel + variabelendeel.
- `references/expressies-en-operatoren-referentie.md` — expressies, rekenkundige operatoren,
  aggregaties, afronding, begrenzing, literals en predicaten (de exacte taalpatronen).
- `references/vertaalpatronen.md` — de brug: JAS-klasse → GegevensSpraak/RegelSpraak, hoe je
  een wetsanalyse-`rapport.json` inleest, en het standalone-pad vanuit wettekst.
- `references/review-checkpoints.md` — het `model.json`-datacontract en de iteratieve reviewlus.
