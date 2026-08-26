# ADR-0017: Cross-service contracten — elke consument genereert zijn eigen client

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

ADR-0002 stelt vast dat een contract tussen twee services een eigen, expliciet geversioneerd
artefact is — nooit iets dat ontstaat doordat twee services dezelfde code importeren — maar
liet open hoe dat er concreet uitziet. Binnen één service bestaat het contractmechanisme al
(ADR-0011: schema → OpenAPI → gegenereerde types); de vraag is of en hoe dat mechanisme zich
uitbreidt over de servicegrens heen.

## Beslissing

- Elke service die via HTTP geconsumeerd wordt, publiceert zijn OpenAPI-schema (`openapi.json`)
  als op zichzelf staand artefact — hetzelfde bestand dat ADR-0011 al binnen de service
  genereert.
- Een consumerende service genereert daaruit zijn **eigen** typed client, los per consument —
  nooit een gedeeld packagetje dat twee services samen importeren (dat zou ADR-0002 schenden).
  Voor TypeScript-consumenten: `openapi-typescript`, zoals al binnen een service (ADR-0011).
  Voor Python-consumenten: `datamodel-code-generator`, dat alleen de Pydantic-modellen
  genereert — geen HTTP-callcode. De aanroep zelf (inclusief timeout/retry/error-boundary,
  ADR-0014) blijft met de hand geschreven, consistent met ADR-0011's principe van expliciete
  mapping zonder impliciete magie.
- Versiekeuze is expliciet: een consument genereert tegen een specifieke versieprefix (`/v1/`,
  ADR-0010). Een upgrade naar een nieuwere versie is een bewuste, aparte actie in de
  consumerende service — nooit automatisch of stilzwijgend.
- **Schema-toegang:** zolang services in dezelfde monorepo zitten, leest een consument het
  schema van de producent via een relatief pad. Zodra een service als eigen repo wordt
  losgetrokken (zie `werkwijze/CLAUDE.md` §Een nieuw project starten voor het precedent),
  verandert dat naar een gepubliceerd endpoint (`/v{n}/openapi.json` op een draaiende
  instantie, of een los artefact) — dat is dan een aanpassing aan het generatiescript van de
  consument, geen principiële wijziging aan dit ADR.

MCP-gebaseerde cross-service-contracten vallen hier niet onder — die lopen al via ADR-0013/0014
(MCP-tool-schema + contracttest), een ander protocol met zijn eigen contractvorm.

## Consequenties

- Contractdrift tussen services wordt net zo mechanisch gevangen als binnen één service — een
  consument met een verouderd gegenereerd bestand toont dat in zijn eigen CI (ADR-0016 stap 2),
  niet pas bij een runtime-fout bij een andere partij.
- Geen gedeelde package om tussen services te versiebeheren — elke consument beslist zelf
  wanneer hij opnieuw genereert.
- Nadeel, bewust geaccepteerd: dezelfde producer-wijziging kan meerdere consumenten raken die
  elk apart moeten regenereren — geen automatische propagatie. Dat is de prijs voor
  onafhankelijk deploybare services (ADR-0002); een gedeelde package zou die onafhankelijkheid
  ondermijnen.
- Nadeel, bewust geaccepteerd: twee generatoren in gebruik (`openapi-typescript` voor TS,
  `datamodel-code-generator` voor Python) in plaats van één — geaccepteerd omdat er geen
  volwassen, breed gebruikt Python-equivalent van `openapi-typescript` bestaat dat zowel
  modellen als callcode consistent met ADR-0011's "expliciete mapping"-principe genereert.
