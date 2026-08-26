# Harness-diagnose — vier hendels bij een falende analyse

Komt een analyse onbevredigend uit, dan is de reflex om het model te verdenken ("het
classificeert dom"). Meestal zit de fout niet in het model maar in de **harness**: de
infrastructuur eromheen. Het model is de motor; de harness is de rest van de auto — de
databron, de procesregie, de remmen en de begrenzing. Een goed gebouwde harness laat een
model slim lijken; een slechte harness laat het falen.

Deze skill heeft vier hendels die je bij een storing systematisch langsloopt, in volgorde:
**Context** (wat zag het model?), **Tools** (wat kon het doen?), **Loop** (hoe bewoog het?)
en **Governance** (wat hield het in toom?). Bij elke hendel staat hieronder de
diagnosevraag en waar die in dit project aan vastzit. De snelle symptoom→hendel-tabel
onderaan is de ingang als je weinig tijd hebt.

## Wanneer pak je dit erbij — en wanneer niet

Dit is **géén** instrument voor gewone review-feedback. Feedback die niet meteen "akkoord"
is, is het normale, gezonde proces: de iteratieve lus werkt dan precies zoals bedoeld, en
je verwerkt de correctie in de volgende ronde (zie `review-checkpoints.md`, stap 2b/3b in
`SKILL.md`). Dat is geen falen.

Pak harness-diagnose erbij bij **onbetrouwbaarheid of storing** — output die niet via "nog
een reviewronde" hoort te ontstaan:

- verzonnen of geparafraseerde wettekst die als citaat wordt gepresenteerd;
- een JAS-klasse die niet in `references/jas-klassen-referentie.md` staat;
- de skill die de reviewstop overslaat of zonder bevestiging doorloopt;
- de MCP die niets (of een fout) teruggeeft;
- de §4-vrije-tekstvelden (reviewlog-samenvattingen, aandachtspunten) die bij opnieuw
  bouwen van `rapport.json` zonder de invul-flags leeglopen;

… óf wanneer de lus zélf niet convergeert (dezelfde correctie landt na meerdere rondes
niet, of markeringen verschuiven steeds).

Kort onderscheid: *"deze markering moet Rechtsfeit zijn, geen Rechtsbetrekking"* is gewone
review — verwerken in de volgende ronde. *"Dit citaat staat niet letterlijk in de wet"* of
*"deze klasse bestaat niet"* is een Context-falen — diagnose. Kernvraag steeds:
**gaat het om inhoudelijke verfijning (normaal) of om onbetrouwbaarheid/storing (diagnose)?**

## 1. Context — wat zag het model?

**Diagnosevraag:** kreeg het model het juiste artikel + de juiste JAS-klassen, in de juiste
vorm, op het juiste moment? Het gaat niet alleen om ontbrekende data, maar ook om
presentatie: te veel ruis verdrinkt het signaal.

Waar dit in deze skill aan vastzit:

- **Brongetrouwheid.** Werkt het model met de letterlijk opgehaalde wettekst, of met
  geheugen? Verzonnen tekst of een parafrase-als-citaat is bijna altijd een contextfout: de
  letterlijke tekst zat niet (goed) in beeld.
- **`references/jas-klassen-referentie.md` als gesloten lijst.** Een niet-bestaande klasse betekent
  meestal dat de dertien JAS-klassen niet (volledig) geraadpleegd waren.
- **De splitsing `references/` versus `docs/`.** De `references/` zijn de operationele
  samenvatting; `docs/` de volledige onderbouwing. Mist een vuistregel, kijk of die in
  `references/` stond of verstopt zat in `docs/`, waar de skill niet standaard kijkt.
- **Brondefinities.** Verwijst de bepaling naar een gedefinieerde term, dan moet het
  definitieartikel opgehaald zijn (via `wettenbank_zoekterm`). Ontbreekt dat, dan analyseert
  het model met de verkeerde betekenis in context.
- **Context-opbouw over rondes.** `analyse.json` en de feedback stapelen per ronde. Bij
  ronde 4-6 dreigt overload: het belangrijke signaal verdrinkt. Een analyse die juist
  *slechter* wordt naarmate de rondes vorderen, wijst hierop.
- **Context-druk bij veel bronnen (werkset-discipline).** Een werkgebied met veel bronnen
  laat de hoofdcontext vollopen: elke `wettenbank_artikel`-respons is ~5–50 KB. Houd de
  werkset klein:
  - Laad de `references/` **één keer** aan het begin; herhaal ze niet per bron.
  - **Activiteit 2 per bron via een sub-agent.** Laat een sub-agent de volledige
    wettekst van bron X markeren/classificeren en alléén het gemarkeerde resultaat
    (markeringen + verwijzingen, niet de leden-tekst) terugmelden. Zo blijft de brontekst
    van afgeronde bronnen uit de hoofdcontext terwijl je bron Y doet.
  - Lees een afgeronde `werk/.../analyse.json` niet onnodig in z'n geheel opnieuw in;
    werk gericht met de id's. Activiteit 3 werkt werkgebied-breed op de **markeringen**,
    niet op de volledige leden-tekst — citeer daar uit de markering, niet uit een
    her-opgehaald artikel.
  Symptoom dat hierop wijst: kwaliteitsverlies of trager/duurder worden naarmate er
  bronnen bijkomen, of het model dat brontekst van een eerdere bron door elkaar haalt.

## 2. Tools — wat kon het model doen?

**Diagnosevraag:** had de agent het juiste actieoppervlak, én begreep het de volgorde en de
veilige inzet ervan?

Het actieoppervlak van deze skill:

- **MCP-keten:** `wettenbank_zoek` → `wettenbank_structuur` → `wettenbank_artikel`
  (→ `wettenbank_zoekterm` voor brondefinities). De volgorde is geen toeval: zonder eerst de
  structuur klopt het artikelnummer of het pad vaak niet.
- **CLI-scripts:** `scripts/review_server.py` (review-checkpoint),
  `scripts/build_rapport_json.py` (combineert de gevalideerde `analyse.json`'s tot
  `rapport.json`) en `scripts/rapport_server.py` (HTML-viewer + Markdown-export).

Veelvoorkomende toolfouten:

- MCP verbindt niet — controleer met `claude mcp list` (verwacht `✓ Connected`) vóór je het
  model verdenkt.
- Verkeerde `bwbId` of jci-`bronreferentie`, of structuur niet eerst opgehaald → verkeerd
  of leeg artikel.
- `build_rapport_json.py` opnieuw gedraaid zónder de §4-flags
  (`--reviewlog-act2/-act3/--aandachtspunten`): de vrije-tekstvelden in `rapport.json` lopen
  dan leeg (zie ook Governance).

## 3. Loop — hoe bewoog de agent?

**Diagnosevraag:** had de agent een helder proces om resultaten te evalueren, met duidelijke
stopcondities — of liep het op hol?

De lus van deze skill is bewust begrensd:

- **De vaste stappen:** activiteit 2 → checkpoint → activiteit 3 → checkpoint → rapport.
- **Stopconditie:** `feedback.json` met `status: "akkoord"` én zonder `items`/`algemeen` =
  klaar. Stopt de skill te vroeg (bij feedback die er nog is) of juist niet (negeert
  akkoord), dan zit de fout in hoe de stopconditie wordt gelezen.
- **Veiligheidscap:** maximaal 6 rondes tegen "op hol slaan". Loopt het tegen die cap aan,
  dan convergeert de lus niet — dat is zelf een diagnosesignaal (zie Context: landt de
  correctie wel in de volgende `analyse.json`? zijn de id's stabiel?).

## 4. Governance — wat hield het in toom?

**Diagnosevraag:** welke acties mochten automatisch, welke vereisten goedkeuring, en wat
moet volledig buiten bereik blijven?

De begrenzing in deze skill:

- **Human-in-the-loop als harde stop.** De skill gaat niet door zonder bevestiging van de
  analist. Loopt ze tóch door, controleer of `WETSANALYSE_NO_REVIEW=1` ten onrechte in de
  omgeving staat (die vlag is alleen voor geautomatiseerde evals bedoeld).
- **Rapport gegenereerd, niet overgetypt.** `build_rapport_json.py` combineert de
  gevalideerde `analyse.json`'s van de hoogste reviewronde tot `rapport.json`; de
  deterministische secties 0-3 komen brongetrouw uit die bestanden, het model levert alleen
  synthese in de §4-vrije-tekstvelden (via de flags of de viewer). Dat begrenst de blast
  radius — feiten verzinnen in secties 0-3 hoort architectonisch onmogelijk te zijn.
  Verschijnen er tóch afwijkingen daar, of lopen de §4-velden leeg, dan is er buiten de
  generator om gewerkt of zonder de invul-flags herbouwd.
- **Brongetrouwheid = out-of-bounds.** Tekst verzinnen of een parafrase als citaat opvoeren
  is geen stijlkwestie maar een grensoverschrijding.
- **Permissie-allowlist.** De krappe, machine-lokale allowlist begrenst wat zonder prompt
  mag draaien.

## Snelle diagnosetabel

| Symptoom | Verdachte hendel |
| --- | --- |
| Verzonnen wettekst / parafrase als citaat | Context (bron niet letterlijk) of Tools (verkeerde artikel-call) |
| Onbestaande JAS-klasse | Context (`jas-klassen-referentie.md` niet geraadpleegd) |
| Brondefinitie gemist | Tools (`wettenbank_zoekterm`/definitieartikel niet opgehaald) |
| Leeg of verkeerd artikel | Tools (verkeerde `bwbId`, structuur niet eerst opgehaald, MCP niet verbonden) |
| Skill loopt door zonder review | Governance (`WETSANALYSE_NO_REVIEW` lekt) of Loop (stopconditie verkeerd gelezen) |
| Eindeloze of te vroeg afgebroken rondes | Loop (stopconditie / 6-rondencap) |
| Analyse wordt slechter over de rondes | Context (overload) of Loop (feedback landt niet) |
| §4-vrije tekst verdwenen / afwijking in secties 0-3 | Governance/Tools (`build_rapport_json.py` zonder §4-flags herbouwd of buiten de generator om gewerkt) |
| Markeringen/begrippen verschuiven tussen rondes | Tools/Loop (instabiele id's) |
