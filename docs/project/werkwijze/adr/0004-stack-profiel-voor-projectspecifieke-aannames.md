# ADR-0004: Stack-profiel voor projectspecifieke aannames

**Status:** geaccepteerd
**Datum:** 2026-08-10 <!-- consequenties bijgewerkt 2026-08-12, toen de resterende skills de topologie uit dit bestand gingen lezen -->

## Context

De skills waren geschreven met precies één concrete stack in gedachten: één ORM-class die
tegelijk tabel en contract is, generatie naar precies één frontend, en alles in één
deploy-eenheid. Die aannames stonden hard gecodeerd in de regels zelf — "de ene bron" wás een
class van een specifieke ORM, "de" API-map en "de" frontend-map waren enkelvoud.

Een project met een andere architectuur kon die regels dan niet volgen. Niet omdat het
onderliggende principe ("vorm op één plek, expliciet, vóór gedrag") niet zou gelden, maar omdat
de regel één concrete vorm ervan als enige mogelijkheid beschreef. Voor déze werkwijze is dat
geen theoretisch bezwaar: meerdere services (ADR-0002) betekent per definitie dat er geen "de"
API-map bestaat.

De rest van de werkwijze (Verificatie-principe, Simplify-stap, PR-triage-staatmachine,
story-review-checklist, "duplicatie pas na de tweede implementatie", de ADR-praktijk zelf) is
wél stack-onafhankelijk — het gaat specifiek om de regels die een concrete implementatievorm
noemen in plaats van een principe uit te drukken.

## Beslissing

Een projectspecifiek artefact — `docs/architectuur/stack-profiel.md`, gekopieerd uit
`werkwijze/docs/architectuur/stack-profiel.TEMPLATE.md` — legt de antwoorden vast op de vragen
die een skill anders stilzwijgend zou aannemen: de ene bron, contractgeneratie, feature-eenheid,
dunne verzamelaars, topologie, migraties, frontend(s) en codestandaard.

De skills verwijzen naar dat bestand in plaats van een stack hard te coderen. Zonder ingevuld
stack-profiel is `feature-bouwen` regel 3 een expliciete stop — geen impliciete aanname.

## Consequenties

- Elk project moet dit bestand invullen vóór er gebouwd wordt. Dat is een extra stap bij de
  start, bewust geaccepteerd: de alternatieve kosten (een skill die stilzwijgend de verkeerde
  stack aanneemt en dat pas bij de review zichtbaar wordt) zijn hoger.
- De skills die dit bestand nu lezen: `feature-bouwen` (regel 2, 3, 4, 7, 8), `code-review`
  (regel 1), `architectuur-audit` (regel 1-4), `frontend-bouwen` (regel 1, 6) en
  `dependency-updates` (regel 1). `CLAUDE.md` §Documentatiestructuur en §Codestandaard doen
  hetzelfde voor de mappenstructuur en de lintconfiguratie.
- Een skill die iets aanneemt wat niet in de template staat, is een gat in de template — vul de
  template aan in plaats van de aanname in de skill te laten staan. De template is daarmee de
  canonieke lijst van "wat een project zelf moet beslissen".
- `stack-profiel.md` is geen ADR: het legt vast wát een project gekozen heeft, niet waarom.
  Blijkt een keuze een echte afweging met nadelen te zijn, dan hoort daar een ADR bij in het
  project zelf.
- **Nog niet ingelost:** `voorbeeld/wetsanalyse/` heeft nog geen ingevuld `stack-profiel.md`,
  omdat die referentie-implementatie nog geen code bevat. Zolang dat zo is, bestaat er in deze
  repo geen voorbeeld van een ingevuld profiel — alleen de template met de vragen. Dat staat als
  open punt in `BACKLOG.md`.
