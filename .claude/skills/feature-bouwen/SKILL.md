---
name: feature-bouwen
description: >-
  Contract-first werkwijze voor het bouwen van een nieuwe feature vanuit een user story, of het
  uitbreiden van bestaand gedrag. Gebruik deze skill bij "implementeer deze story", "bouw een
  endpoint/domein voor X", "voeg een nieuwe tabel/feature toe", elke keer dat een gevalideerde
  user story of gedragsuitbreiding daadwerkelijk gebouwd gaat worden, én wanneer `pr-triage`
  een blocking review-bevinding laat oplossen — ook een fix op een bestaande PR volgt deze
  regels, geen aparte ad-hoc aanpak. Niet voor het toetsen van een nieuwe, nog niet gebouwde
  story op volledigheid (zie `story-review`, die loopt hieraan vooraf), niet voor het reviewen
  van een bestaande pull request (zie `code-review`), en niet voor een projectbrede zoektocht
  naar duplicatie (zie `architectuur-audit`).
---

# Feature bouwen — contract-first

**Trigger:** een nieuwe user story, een uitbreiding van bestaand gedrag, of `pr-triage` die een
blocking review-bevinding laat verwerken. Is de story nog niet gecheckt op volledigheid, draai
dan eerst `story-review`. Vraagt de story ook een UI: `frontend-bouwen` loopt ná regel 1-6
hieronder (schema, keten, logica, tests zijn dan klaar), vóór regel 9 (zie daar).

Lever nooit af zonder de checklist in regel 9 te doorlopen — zonder het controleerbare spoor
dat daar verplicht is, behandelt `code-review` de PR als onvolledig.

## Stappen (1-6)

1. **Schemabeslissing.** Leg de story en acceptatiecriteria vast in
   `docs/stories/<nummer>-<naam>.md`, met expliciet welke velden en types nodig zijn. Abstraheer
   niet vooruitlopend op een patroon dat nog niet is gezien — zie regel 8 voor wanneer
   duplicatie wél een probleem wordt. (Is de story al door `story-review` gegaan, dan is dit al
   gedaan — controleer alleen dat de story nog actueel is.)

2. **Kies de service, dan isoleer.** Een feature hoort bij precies één service (ADR-0002).
   Welke services er zijn en waar ze staan, leest `stack-profiel.md` §Topologie voor — is dat
   niet eenduidig af te leiden, vraag het dan, en verdeel gedrag nooit stilzwijgend over twee
   services. Binnen de gekozen service: nieuwe feature → nieuwe map
   `<service>/app/features/<naam>/` (of wat §Feature-eenheid daar zegt). Nooit een tabel of
   route rechtstreeks in een verzamelbestand van de service (het routes-samenvoegpunt, de
   database-setup) — die blijven dun, alleen samenvoegers.

3. **Schrijf de ene bron, zoals dit project 'm heeft vastgelegd in
   `docs/architectuur/stack-profiel.md` (§De ene bron).** Bestaat dat bestand nog niet: dat is de
   eerste vraag om te beantwoorden, geen aanname om impliciet te maken — kopieer
   `stack-profiel.TEMPLATE.md` uit `werkwijze/docs/architectuur/` naar
   `docs/architectuur/stack-profiel.md` en vul 'm in vóór je verdergaat.

   Wat de vorm ook is, deze eisen gelden altijd:

   - **Eén plek per entiteit.** Tabeldefinitie en het contract dat de buitenwereld ziet, komen
     uit dezelfde bron — geen tweede, met de hand bijgehouden kopie van dezelfde velden.
   - **Binnen één service.** De ene bron geldt per service, niet projectbreed (ADR-0002): twee
     services delen hun schema niet via een import, maar via een expliciet contract.
   - **Onderscheid wat een client mag sturen van wat hij terugkrijgt** — dat zijn twee
     verschillende vormen, ook als ze nu toevallig dezelfde velden hebben.
   - **Geen gedragslogica hier.** Een schema kan "mag dit nu wel" niet uitdrukken (regel 5).
   - **Wees scherp op precisie**: een `str` waar een gesloten verzameling bedoeld is, genereert
     verderop in de keten een losse `string` en geen strikter type.

   De voorziene invulling voor deze werkwijze is SQLAlchemy Core + Pydantic, met
   `openapi-typescript` als generatiestap (`BACKLOG.md` §Core) — hoe die combinatie er concreet
   uitziet is nog niet uitgewerkt en is dus precies wat `stack-profiel.md` §De ene bron per
   project moet vastleggen, niet iets om hier impliciet aan te nemen.

4. **Genereer de keten** van de service waar je in werkt: het API-schema uit de ene bron, en
   daaruit de types voor de consumers. Welk script dat is en welke bestanden het schrijft, staat
   in `stack-profiel.md` §Contractgeneratie; zegt dat "nee" (geen generatie), dan vervalt deze
   regel en schrijf je het contract met de hand — maar dan wél op één plek, met dezelfde eis uit
   regel 3.

   Bewerk gegenereerde bestanden nooit met de hand — draai het script opnieuw. Commit de output
   mee. Genereert de wijziging ook een contract dat een ándere service consumeert, dan is dat
   geen automatische stap: zie §Wat dit niet oplost.

5. **Schrijf wat niet uit de vorm volgt.** Auth-checks, validatie voorbij het schema,
   businessregels — in de routelaag van de feature, niet bij het schema. Aparte,
   hand-geschreven code per concern, geen duplicatie met regel 3.

6. **Test gedrag, niet vorm.** Vorm is al gegarandeerd door regel 3-4. Test de
   acceptatiecriteria en de randgevallen: de businessregel zelf, wat er gebeurt als je hem
   probeert te omzeilen, 404's op onbekende id's.

## Situationeel (7-8)

7. **Bestaande database? Migratie apart.** Volg `stack-profiel.md` §Migraties van de service
   waar je in werkt. Let op de klassieke val: een "maak ontbrekende tabellen aan bij het
   opstarten"-mechanisme doet geen ALTER en geen kolom-migratie op een bestaande tabel. Zodra
   dit tegen een bestaande productiedatabase draait, hoort er een echte migratiestap te zijn
   (Alembic of gelijkwaardig), los van dit patroon. Raakt de migratie een database die meer dan
   één service gebruikt, dan is het geen zaak van deze service alleen — dat is een
   deploy-volgorde-probleem tussen services, geen stap in deze skill.

8. **Gedeelde logica: opportunistisch verwijzen, niet vooruitlopend abstraheren.** Duplicatie
   is pas een probleem ná de tweede, onafhankelijke implementatie van hetzelfde patroon — niet
   vóór de eerste. Herken je tijdens het bouwen dat deze feature een patroon herhaalt van een
   feature die je al kent (de story verwijst ernaar, of je hebt 'm net gelezen): verwijs naar de
   bestaande implementatie in plaats van te kopiëren. Twee gevallen, met een andere bestemming:

   - **Het patroon hoort bij één entiteit die een andere feature al bezit** (bijvoorbeeld:
     "bestaat deze analyse?" hoort bij `Analyse`, dat eigendom is van `analyseren`) → maak de bestaande
     functie openbaar in de eigenaar-feature (geen underscore-prefix), importeer 'm vanuit de
     consumerende feature. Geen `shared/`-geval: er is een duidelijke eigenaar.
   - **Het patroon heeft geen natuurlijke eigenaar** (een generieke implementatie die evengoed
     bij feature A als bij feature B had kunnen ontstaan) → naar de `shared/`-map van diezelfde
     service (`<service>/app/shared/<naam>.py`).

   Beide routes gelden alleen **binnen één service**. Herhaalt een andere service hetzelfde
   patroon, dan is dat geen import maar een aparte afweging (gedeelde bibliotheek of bewuste
   duplicatie) — zie ADR-0002 en `architectuur-audit` regel 2.

   Ga hiervoor **niet** het hele project doorzoeken (dat staat haaks op regel 2) — systematisch
   zoeken naar duplicatie die je nog niet kende is `architectuur-audit`'s taak, niet die van
   deze skill. Gebruik je een van de twee routes: zet in de story van *deze* feature de regel
   "gebruikt `shared/<naam>.py`, zie daar" of "gebruikt `<feature>.<module>.<functie>`, zie daar"
   — die terugverwijzing verwacht `architectuur-audit` aan te treffen, en helpt andere features
   het te vinden zonder te hoeven zoeken.

## Afleveren (9-10)

9. **Checklist — doorloop dit expliciet, sla geen stap over:**

   - [ ] Tests groen (regel 6).
   - [ ] Generatieketen gedraaid, geen diff op de gegenereerde bestanden (regel 4).
   - [ ] Vroeg de story ook een UI: `frontend-bouwen` is afgerond (inclusief zijn eigen
     E2E-test-eis).
   - [ ] Check `CLAUDE.md` §Instellingen — Simplify bij feature-bouwen:
     - `ja` — draai `/simplify` daadwerkelijk (ingebouwde Claude Code-skill, niet zelf
       herimplementeren: vier parallelle checks — reuse, simplificatie, efficiency, altitude —
       op de wijzigingen sinds de vorige `/simplify`-ronde op deze PR, exclusief de
       gegenereerde bestanden). Bevindingen direct toepassen. Expliciet **geen correctheid**,
       dat blijft `code-review`'s taak. Geen kortsluitroute op basis van "de wijziging is klein"
       — zie §Bekende valkuilen voor waarom juist kleine wijzigingen dit risico lopen.
     - `nee` — sla de daadwerkelijke check over, maar niet stilzwijgend: ga direct door naar de
       volgende stap.
   - [ ] Het commit-bericht (bij een fix-commit op een bestaande PR) of de PR-beschrijving (bij
     de eerste keer) bevat één van deze vier regels — dit is de canonieke lijst, andere skills
     verwijzen hiernaar in plaats van 'm te herhalen:
     - `Simplify: <bevindingen>` — er was iets te verbeteren, en dat is gebeurd.
     - `Simplify: geen` — gedraaid, niets gevonden.
     - `Simplify: overgeslagen (instelling staat op nee)` — de instelling stond uit.
     - `Simplify: n.v.t. (<reden>)` — deze wijziging bevat **geen productiecode** om op te
       toetsen: puur documentatie, CI-configuratie, of testbestanden zonder bijbehorende
       implementatiewijziging. Nieuwe productiecode in een nieuwe service of een nieuw bestand
       valt hier **niet** onder — `/simplify` controleert ook nieuwe code op vereenvoudiging.

     Dit is het enige controleerbare bewijs dat deze stap is afgehandeld — geen aanname die je
     zelf mag maken. Zonder een van deze vier regels behandelt `code-review` een PR die
     feature- of frontend-code raakt als onvolledig.

   Vink deze lijst niet stilzwijgend af door meteen naar git-commando's te gaan (zie §Bekende
   valkuilen).

10. **Afleveren.** Twee verschillende acties, afhankelijk van de trigger:

    - **Eerste keer** (nieuwe story/uitbreiding, inclusief een eventuele `frontend-bouwen`-fase
      erin): **open de PR.** Vanaf dat moment is `pr-triage` aan zet.
    - **Fix op een blocking bevinding** (`pr-triage` stuurde je hierheen): de PR bestaat al —
      **push een commit op die bestaande PR**, open geen nieuwe. `pr-triage` pikt de nieuwe
      commit vanzelf weer op (zijn trigger is "PR aangemaakt, of krijgt een nieuwe commit").

## Bekende valkuilen

- **`datetime.utcnow()` is deprecated** — gebruik `datetime.now(UTC)`.
- **`openapi-typescript` trekt via `@redocly/openapi-core` soms een kwetsbare `js-yaml`-versie
  mee** zonder beschikbare fix. Dev-only build-tooling — risico is acceptabel, raakt nooit de
  productie-runtime.
- **ORM-specifieke valkuilen horen niet hier maar in `stack-profiel.md`** — lazy-loading van
  relaties, forward-refs in type-annotaties en soortgelijke voetangels verschillen per ORM.
  Noteer ze bij het stack-profiel van het project dat ze tegenkomt; deze skill blijft
  stack-onafhankelijk.
- **Zonder het eigenaar/ownerless-onderscheid in regel 8 verzandt gedeeld gedrag in een
  asymmetrische herimplementatie**: een tweede feature die dezelfde check nodig heeft als een
  bestaande (bijvoorbeeld "bestaat deze entiteit?") krijgt dan al snel een eigen, private
  kopie in plaats van de bestaande functie te hergebruiken, simpelweg omdat er geen duidelijke
  "plek" leek te zijn om naartoe te verwijzen.
- **Een checklist-item dat alleen als tekst in een lijst staat, is makkelijk te missen zodra de
  rest van het werk klaar aanvoelt** — met name vlak vóór het committen, wanneer de aandacht al
  naar de volgende taak is verschoven. Vandaar de expliciete checklist in regel 9 én de
  verplichte spoor-regel in het commit-/PR-bericht: een lijst zonder controleerbaar bewijs is
  geen vangrail (zie `CLAUDE.md` §Verificatie-principe).

Kom je een nieuwe, structurele valkuil tegen (niet een eenmalige bug, maar iets dat deze skill
raakt): voeg hem hier toe als een generieke les, niet als een verslag van één specifieke build.

## Wat dit niet oplost

- **Migratie van een bestaande productiedatabase** — Alembic, los van dit patroon (regel 7).
- **Contracten tussen services** — de generatieketen dekt alleen wat binnen déze service loopt
  (regel 3, ADR-0002). Hoe het contract tússen twee services vastligt en geversioneerd wordt, is
  een open punt in `BACKLOG.md` §Core — geen geaccepteerde grens, maar nog geen antwoord.
- **Precisie die de bron zelf niet heeft** — een `str` in plaats van een `Literal[...]`
  genereert een losse `string`, geen strikter type. Wees scherp in regel 3.
