# ADR-0010: API-versioning — URL-prefix-mechanisme

**Status:** geaccepteerd
**Datum:** 2026-08-12 (uitfaseerbeleid toegevoegd 2026-08-12)

## Context

Een service-contract evolueert. Zonder een expliciete versiestrategie breekt een
schemawijziging (veld hernoemd/verwijderd, gedrag gewijzigd) stilzwijgend bestaande consumers
zodra de nieuwe versie live gaat — met meerdere services (ADR-0002) is dat geen incident meer
binnen één team, maar een breuk tussen onafhankelijk deploybare eenheden.

## Beslissing

Elke service publiceert zijn contract onder een expliciete versieprefix in de URL (`/v1/...`).

- Een **backward-incompatibele** wijziging (veld verwijderd/hernoemd, betekenis gewijzigd,
  verplicht veld toegevoegd) verhoogt de prefix (`/v2/...`) **naast** de bestaande, niet in
  plaats ervan — de oude prefix blijft draaien tot expliciet uitgefaseerd.
- Een **backward-compatibele** toevoeging (nieuw optioneel veld, nieuw endpoint) leidt niet tot
  een versiebump.

**Uitfaseerbeleid.** Een oude versieprefix blijft minimaal 90 dagen bereikbaar nadat de
opvolger live is gegaan. Zodra de opvolger live is, krijgt elke response op de oude prefix een
machine-leesbare aankondiging (een `Deprecation`/`Sunset`-header, in de stijl van RFC 8594) —
niet pas vlak vóór het daadwerkelijk verwijderen. De service-eigenaar mag de oude versie
uitfaseren zodra zowel de aankondigingstermijn verstreken is, als er geen bekend verkeer meer op
de oude prefix binnenkomt (te meten via de gestructureerde logs, ADR-0012) — de eerste
voorwaarde alleen is niet genoeg als er nog actieve consumers zijn.

## Consequenties

- Consumers breken nooit stilzwijgend door een deploy van de aanbiedende service.
- Meerdere versies van dezelfde service kunnen tijdelijk naast elkaar draaien tijdens een
  migratie van consumers.
- Consumers krijgen een tijdige, machine-leesbare waarschuwing vóór een oude versie verdwijnt,
  in plaats van een harde breuk.
- Nadeel, bewust geaccepteerd: een service kan tijdelijk twee versies van dezelfde routes moeten
  onderhouden, minimaal 90 dagen. Die 90 dagen is een vaste ondergrens die niet per geval
  heronderhandeld wordt — voor een interne service met bekende, tembare consumers kan dat langer
  zijn dan strikt nodig, maar een vaste regel voorkomt dat "we versnellen het deze ene keer" de
  norm wordt.
