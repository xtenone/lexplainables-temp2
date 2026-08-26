# ADR-0002: Meerdere, onafhankelijk deploybare services

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Vertical slicing (ADR-0001) koppelt features op codeniveau al los. De vervolgvraag is of ze
daarnaast ook als aparte deploy-eenheden draaien, of samen in één proces.

Deze werkwijze is geschreven voor applicaties waarin dat eerste al vaststaat: een synchroon
request-pad naast langlopend achtergrondwerk (LLM-orkestratie, async jobs), met verschillende
schaal- en faalkarakteristieken. In één proces bepaalt de traagste component het tempo en de
uptime van het geheel — dat is precies wat deze applicaties niet kunnen hebben.

## Beslissing

Een applicatie bestaat uit meerdere, onafhankelijk deploybare services. Wat daarmee vastligt:

- **Elke service is zijn eigen deploy-eenheid**, met een eigen CI/CD-pijplijn — een wijziging in
  de ene service dwingt geen deploy van de andere af.
- **Binnen een service geldt ADR-0001 onverkort**: vertical slicing per feature, met dunne
  verzamelbestanden die geen domeinkennis dragen. Vertical slicing is dus geen alternatief voor
  de service-indeling, het is de indeling *binnen* elke service.
- **Een service is de grens van "de ene bron".** Contractgeneratie loopt binnen één service, van
  diens schema naar diens consumers. Een contract tussen twee services is een eigen, expliciet
  geversioneerd artefact — nooit iets dat ontstaat doordat twee services dezelfde code
  importeren, want dan zijn ze niet meer los deploybaar.

## Consequenties

- Alle skills die "de" API-map, "de" database of "de" frontend als vanzelfsprekend behandelen,
  moeten per service gelezen worden. Welke services er zijn en waar ze staan, legt een project
  vast in `docs/architectuur/stack-profiel.md` §Topologie (ADR-0004) — de skills coderen dat
  niet hard.
- Cross-service contracten en hun versionering zijn hiermee een echt probleem van deze werkwijze
  geworden, geen buiten-scope-verklaring meer zoals bij een enkele deploy-eenheid. De uitwerking
  staat als open punt in `BACKLOG.md` §Core (API-versioning, multi-service topologie).
- Gedeelde code tussen services is een zwaardere afweging dan gedeelde code binnen een service:
  `shared/` binnen één service is een verplaatsing, tussen services is het een gedeelde
  bibliotheek met eigen versionering. `architectuur-audit` behandelt die twee daarom gescheiden.
- **Bewust nog niet besloten in dit ADR:** hoeveel services er zijn, hoe ze heten, en hoe ze
  onderling communiceren (synchroon HTTP, events, of allebei). Dat is een keuze per applicatie,
  en de generieke invulling ervoor staat als open punt in `BACKLOG.md`. Dit ADR legt alleen vast
  dát het er meerdere zijn en wat dat voor de werkwijze betekent.
- Nadeel, bewust geaccepteerd: meerdere services betekent meer infrastructuur per feature
  (aparte pijplijnen, contracten tussen services, meer plekken om te debuggen) dan één
  deploy-eenheid. Dat is de prijs voor onafhankelijk schalen en deployen; voor een applicatie
  zonder die eis is deze werkwijze zwaarder dan nodig.
