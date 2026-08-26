# ADR-0014: MCP-server & -client — twee gescheiden bouwstukken

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een service kan zowel eigen functionaliteit als MCP-tools exposeren (MCP-server) als een
externe MCP-service aanroepen (MCP-client). Dit zijn twee verschillende bouwstukken met andere
faalmodi: een MCP-server die een intern detail lekt via een te ruim tool-schema, versus een
MCP-client die een onbereikbare of tragere externe service niet netjes afvangt en zo de
aanroepende feature meesleurt in de storing.

## Beslissing

**MCP-server-kant:** tools worden geregistreerd in een expliciete, doorzoekbare lijst — geen
impliciete auto-discovery van functies die toevallig aan een decorator hangen. Elk tool-schema
is een eigen contract met dezelfde eisen als een gewoon API-contract (`feature-bouwen` regel 3):
één plek, en een expliciet onderscheid tussen wat een aanroeper mag sturen en wat hij
terugkrijgt.

**MCP-client-kant:** elke aanroep naar een externe MCP-service heeft een eigen error-boundary —
een timeout, een retry met een harde bovengrens, en een expliciete fallback of foutmelding als
de externe service niet (op tijd) reageert. Nooit een onafgevangen exception die de aanroepende
feature laat crashen op een externe dependency.

## Consequenties

- Consistente foutafhandeling ongeacht welke externe MCP-service wordt aangeroepen — een trage
  of onbereikbare externe tool degradeert een feature, hij breekt hem niet.
- Een MCP-server-tool-lijst is in één oogopslag te overzien, zonder de codebase te doorzoeken
  naar decorators.
- Nadeel, bewust geaccepteerd: een aparte error-boundary-laag per MCP-client-aanroep is meer
  code dan een kale aanroep — geaccepteerd omdat een externe dependency per definitie
  onbetrouwbaarder is dan interne code.
