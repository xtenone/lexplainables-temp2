# ADR-0013: Contracttests voor MCP-oppervlakken

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een MCP-tool-schema (input/output van een tool die een service exposeert) is geen
OpenAPI-`response_model` en valt dus buiten de bestaande contractgeneratie en -verificatie
(ADR-0011, `check-generated-types`). Zonder een aparte check kan een MCP-tool-schema
stilzwijgend afwijken van wat een consumer (een andere service, of een extern MCP-cliënt)
verwacht — precies het probleem dat de gewone contractgeneratie al oplost voor OpenAPI, alleen
dan onopgemerkt voor MCP.

## Beslissing

Elke MCP-tool krijgt een contracttest die het tool-schema (input- en outputvorm) verifieert
tegen een vastgelegde verwachting. Deze test hoort bij de service die de tool exposeert — net
als de gewone testverplichting uit `feature-bouwen` regel 6 — niet centraal in een aparte
testsuite. Een wijziging aan een tool-schema zonder bijbehorende test-aanpassing is dus
zichtbaar in dezelfde PR, niet pas bij een consument die stukloopt.

## Consequenties

- MCP-schema-drift wordt net zo mechanisch gevangen als OpenAPI-drift, ondanks dat het een
  ander protocol is.
- Nadeel, bewust geaccepteerd: MCP-tool-schema's worden (nog) niet automatisch gegenereerd
  zoals OpenAPI-schema's dat wel zijn (ADR-0011) — deze contracttest is dus met de hand
  geschreven en onderhouden. Een generatiemechanisme voor MCP-schema's zelf valt buiten dit
  ADR.
