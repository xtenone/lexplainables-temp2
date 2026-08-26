# ADR-0008: Async jobs — claim/lease/reaper/reconcile-bij-herstart

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een achtergrondtaak die door meerdere workers/instanties tegelijk opgepakt kan worden, heeft een
mechanisme nodig om te voorkomen dat twee workers dezelfde taak dubbel uitvoeren, én om een
taak die halverwege crasht (worker valt weg zonder de taak af te melden) alsnog opnieuw op te
laten pakken.

## Beslissing

Een achtergrondtaak doorloopt altijd dezelfde levenscyclus:

- **Claim** — een worker markeert een taak atomisch als "in behandeling door mij", met een
  expliciete lease-vervaltijd.
- **Lease verlengen** — zolang de worker actief met de taak bezig is, verlengt hij de lease
  periodiek.
- **Reaper** — een apart, periodiek proces zet taken met een verlopen lease terug naar
  "opnieuw op te pakken".
- **Reconcile bij herstart** — bij het opstarten van een worker/service controleert het proces
  expliciet op taken die vóór een crash "in behandeling" stonden bij diezelfde worker, niet
  alleen passief op de reaper wachten.

## Consequenties

- Een gecrashte worker verliest nooit stilzwijgend een taak — de lease-vervaltijd is de harde
  bovengrens op hoe lang een taak "vast" kan blijven staan.
- Meerdere workers kunnen veilig parallel dezelfde wachtrij leeglezen zonder dubbel werk.
- Nadeel, bewust geaccepteerd: meer bewegende delen dan een simpele "pak de eerste onbehandelde
  rij"-aanpak — een reaper-proces en een expliciet lease-veld zijn alleen de moeite waard zodra
  er daadwerkelijk meerdere workers of langlopende taken zijn.
