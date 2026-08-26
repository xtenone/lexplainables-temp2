# ADR-0016: CI/CD per service — sjabloon

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Elke service is zijn eigen deploy-eenheid met een eigen CI/CD-pijplijn (ADR-0002). De werkwijze
verwijst al bij naam naar checks die zo'n pijplijn moet leveren (`check-generated-types`,
`check-frontend-e2e-coverage`, `check-python-style`, `check-ts-style`, de testrun), maar het
sjabloon zelf — hoe die checks per service worden opgezet — lag nog niet vast. Dit ADR legt het
sjabloon vast; hoeveel services er daadwerkelijk komen (de matrix zelf) is een aparte, nog open
vraag (`BACKLOG.md` — Multi-service topologie).

## Beslissing

Elke service krijgt een eigen CI-workflowbestand — geen gedeelde monorepo-matrix-job die alle
services in één workflow bundelt. Elke workflow bevat minimaal, in deze volgorde:

1. Codestandaard (ADR-0003) — lint + format-check.
2. Contractgeneratie-check (ADR-0011) — de gegenereerde types komen overeen met het schema.
3. Testrun.
4. Alleen als de service een frontend bedient: E2E-dekking + Playwright.

Een wijziging in service A start nooit de CI van service B — elke workflow triggert alleen op
wijzigingen binnen zijn eigen servicemap (`paths:`-filter). Het workflowbestand zelf staat,
zoals GitHub Actions vereist, altijd op `.github/workflows/` op de repo-root — dat is geen
keuze, GitHub leest workflows nergens anders (zie ook `CLAUDE.md` §Geen CI op deze repo voor
dezelfde beperking). "Eigen workflowbestand per service" betekent dus: één los bestand per
service in die map (bv. `api-ci.yml`, `frontend-ci.yml`), niet één bestand fysiek in de
servicemap — de scoping zit in de bestandsnaam en de `paths:`-filter, niet in de locatie.

## Consequenties

- Een nieuwe service toevoegen betekent een nieuw workflowbestand kopiëren en aanpassen, geen
  wijziging aan een groeiend centraal workflowbestand.
- Nadeel, bewust geaccepteerd: meer, kleinere workflowbestanden dan één grote matrix —
  geaccepteerd omdat dit direct aansluit bij "elke service is zijn eigen deploy-eenheid"
  (ADR-0002); een gedeelde matrix zou die onafhankelijkheid weer ondermijnen.
- **Bewust nog niet besloten in dit ADR:** de daadwerkelijke matrix — welke services er zijn,
  dus hoeveel van deze workflowbestanden er komen. Dat wacht op de topologiebeslissing
  (`BACKLOG.md`).
