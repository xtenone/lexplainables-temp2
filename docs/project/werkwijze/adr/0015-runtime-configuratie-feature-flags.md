# ADR-0015: Runtime-configuratie / feature-flags

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Instellingen die tijdens bedrijf moeten wijzigen zonder herdeploy (een feature aan/uit, een
drempelwaarde) zijn geen Secrets (ADR-0006: die zijn build-/opstarttijd) en geen gewone
domeindata (ADR-0007's Store-abstractie is voor businessentiteiten, niet voor operationele
knoppen). Zonder een eigen plek voor dit soort configuratie belandt het ofwel als
environment-variabele (vraagt een herdeploy om te wijzigen) ofwel verspreid in domeintabellen
(vermengt operationele instellingen met businessdata).

## Beslissing

Runtime-configuratie staat in een eigen tabel/store, los van domeindata, en is alleen
beschrijfbaar via het admin-authenticatieschema (ADR-0009). Lezen gebeurt via een read-through
cache die invalideert bij een schrijfactie — niet gepolld op een vaste interval, en niet
rechtstreeks uit de database gelezen bij elke request.

## Consequenties

- Een instelling wijzigt zichtbaar binnen één cache-cyclus, zonder herstart.
- Duidelijke scheiding: Secrets voor build-/opstarttijd, Store-abstractie voor domeindata,
  runtime-configuratie voor operationele knoppen die tijdens bedrijf wijzigen.
- Nadeel, bewust geaccepteerd: een extra cache-invalidatiepad om correct te houden —
  geaccepteerd omdat rechtstreeks uit de database lezen bij elke request onnodige
  databasebelasting zou zijn voor iets dat zelden wijzigt.
