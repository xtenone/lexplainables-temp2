# ADR-0012: Observability — baseline (structured logs + correlation-ID)

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Met meerdere services (ADR-0002) is een fout of trage request vaak het gevolg van een keten van
aanroepen over services heen. Zonder een gedeelde, minimale observability-baseline is die keten
achteraf niet te reconstrueren, ook niet met uitgebreide losse logging per service.

## Beslissing

Elke service logt in gestructureerd formaat (JSON, niet vrije tekst) en propageert een
correlation-ID: aangemaakt bij het eerste binnenkomende request, doorgegeven via een header aan
elke uitgaande aanroep naar een andere service. Dit is de minimale, verplichte baseline.

De keuze van het log-/tracing-backend (bijvoorbeeld een OTel-collector, Grafana) en de concrete
dashboards zijn hiermee niet besloten — dat blijft een apart, open backlogpunt.

## Consequenties

- Eén request over meerdere services heen is achteraf te herleiden via één ID, ook zonder een
  volledig tracing-systeem.
- Logs zijn machine-verwerkbaar vanaf dag één, ook vóórdat een centraal logplatform gekozen is.
- Nadeel, bewust geaccepteerd: JSON-logs zijn minder prettig direct leesbaar in een terminal
  tijdens lokale ontwikkeling dan platte tekst — een lokale pretty-printer kan dat compenseren
  zonder het productieformaat te veranderen.
