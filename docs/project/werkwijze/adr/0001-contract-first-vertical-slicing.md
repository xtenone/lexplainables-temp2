# ADR-0001: Contract-first + vertical slicing als basiswerkwijze

**Status:** geaccepteerd
**Datum:** 2026-08-10 <!-- met terugwerkende kracht vastgelegd; dit is de beslissing die aan het begin van dit project al gold -->

## Context

Een service met een database, een API en consumers kan het schema op drie plekken los van
elkaar laten ontstaan (tabel, contract, frontend-type), of het op één plek vastleggen en de rest
genereren. De eerste aanpak (schema-per-laag, met de hand gesynchroniseerd) is de bekendste
faalmodus: de drie versies lopen na een paar wijzigingen vanzelf uit elkaar, meestal pas zichtbaar
als een runtime-fout in productie.

Een tweede, onafhankelijke keuze: features horizontaal indelen (alle modellen bij elkaar, alle
routes bij elkaar) of verticaal (alles voor één feature bij elkaar, inclusief zijn eigen tests).
Horizontale indeling laat gedeelde bestanden onbeperkt groeien met elk nieuw domein erbij.

## Beslissing

Vorm (velden, types) wordt binnen een service op precies één plek vastgelegd — "de ene bron" —
en van daaruit gegenereerd naar de rest (API-schema → TypeScript-types voor de consumers).
Gedrag (businessregels, validatie voorbij het schema) wordt apart, met de hand geschreven, nooit
gegenereerd.

Features worden verticaal georganiseerd: één map per feature, met daarin alles voor die feature
— schema, routes en tests bij elkaar. De verzamelbestanden van een service (het samenvoegpunt
van routes, de database-setup) blijven dun: alleen samenvoegers, geen domeinkennis.

Dit ADR legt het principe vast, niet de technologie. De concrete vorm van "de ene bron", de
naam van de generatiestap en de mappenstructuur per service legt elk project vast in
`docs/architectuur/stack-profiel.md` (ADR-0004). De voorziene invulling voor deze werkwijze —
SQLAlchemy Core + Pydantic + `openapi-typescript` — staat als nog uit te werken punt in
`BACKLOG.md` §Core.

Zie `.claude/skills/feature-bouwen/SKILL.md` voor de volledige, uitvoerbare regelreeks die hier
uit volgt.

## Consequenties

- Eén brontype per entiteit betekent dat een velduitbreiding altijd op dezelfde plek begint —
  geen keuze meer nodig over "waar pas ik dit als eerste aan".
- Genereren dwingt een vaste keten af die in CI gecontroleerd kan worden
  (`check-generated-types`) — dat kan alleen omdat er één bron is om tegen te verifiëren.
- De reikwijdte is één service (ADR-0002): binnen een service is de bron gedeeld, tussen
  services niet. Twee services die dezelfde entiteit kennen, delen die via een expliciet
  contract, niet via dezelfde brondefinitie.
- Nadeel, bewust geaccepteerd: het patroon leunt op een stack waarin schema en contract
  daadwerkelijk uit dezelfde definitie te genereren zijn. Een service in een taal/framework
  waar dat niet kan, vraagt een ander generatiemechanisme — niet alleen een andere
  implementatie van hetzelfde patroon. Dat is per service een eigen keuze, vastgelegd in het
  stack-profiel.
- Nadeel: vertical slicing betekent dat een concept zonder natuurlijke eigenaar (gedeeld tussen
  ≥2 features) een expliciete beslissing vraagt (`shared/` vs. owner-export, zie
  `feature-bouwen` regel 8) — er is geen vanzelfsprekende plek zoals bij een horizontale indeling.
