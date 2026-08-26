# ADR-0003: Codestandaard is geautomatiseerd, geen proza-richtlijn

**Status:** geaccepteerd
**Datum:** 2026-08-10

## Context

Codestijl (opmaak, imports, ongebruikte variabelen) kan als geschreven richtlijn vastgelegd
worden (een stijldocument dat mensen lezen), of als afdwingbare tooling. Met AI als voornaamste
auteur van de code is stijldrift tussen features reëel: elke sessie/model kan net iets anders
formatteren zonder dat iemand het als "fout" herkent, omdat er niets is om tegenaan te
controleren.

## Beslissing

Codestijl wordt afgedwongen via tooling, niet via documentatie: `ruff` (Python) en `eslint` +
`prettier` (TypeScript), beide gecontroleerd in CI (`check-python-style` + `check-ts-style`).
Zie `CLAUDE.md` §Codestandaard en `stack-profiel.md` voor de projectspecifieke config-paden.

## Consequenties

- Consistent met het Verificatie-principe: een regel zonder CI-check of objectieve
  nakijkbaarheid is geen vangrail. Een stijlgids die niemand afdwingt zou precies dat probleem
  zijn.
- Geen aparte checklist-regel nodig in `feature-bouwen` of `code-review` — CI vangt dit
  onafhankelijk van zelfrapportage (been 1 van het Verificatie-principe).
- Deze beslissing leunt volledig op been 1: zonder een CI-workflow die de twee checks
  daadwerkelijk draait, is het weer een stijlgids die niemand afdwingt. Die workflow bestaat in
  deze repo nog niet (`BACKLOG.md` §Core, CI/CD per service) — een project dat de werkwijze
  overneemt, moet 'm zelf opzetten.
- Nadeel, bewust geaccepteerd: de gekozen regels (`ruff`-selectie E/F/I/UP/B met `B008` uit,
  Prettier-defaults) zijn een startpunt, geen uitputtend doordachte stijlgids. Uitbreiden kan
  altijd; een regel die te veel valse positieven geeft, hoort hier expliciet uitgezet te worden
  (zoals `B008`), niet stilzwijgend genegeerd.
