# ADR-0007: Store-abstractie — Protocol-gebaseerde toegang tot domeindata

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een router die rechtstreeks een databasesessie/engine aanroept, koppelt businesslogica hard aan
één opslagimplementatie — moeilijk te unit-testen zonder een echte database, en moeilijk te
vervangen (bijvoorbeeld SQLite in tests, Postgres in productie) zonder de router zelf aan te
passen.

## Beslissing

Voor elk domein dat data opslaat, definieert de feature een Protocol (of vergelijkbare
structurele interface) dat de operaties beschrijft die de router nodig heeft — niet de
databasedetails. De router kent alleen het Protocol; een concrete implementatie (bijvoorbeeld
een Postgres-store) wordt bij het opstarten geïnjecteerd. Tests gebruiken een lichte, in-memory
of SQLite-implementatie van hetzelfde Protocol, zonder de router-code aan te raken.

## Consequenties

- Een router is triviaal te unit-testen zonder een echte database op te tuigen.
- Opslag kan per omgeving verschillen (SQLite lokaal/tests, Postgres productie) zonder een apart
  codepad in de router.
- Nadeel, bewust geaccepteerd: een extra indirectielaag (Protocol + implementatie) per domein,
  ook als er nooit een tweede implementatie komt — geaccepteerd omdat testbaarheid zonder een
  lopende database zwaarder weegt dan het extra bestand.
- Dit vervangt niet de opportunistisch-verwijzen-regel voor gedeelde logica: een Protocol per
  domein voorkomt niet dat twee domeinen toevallig dezelfde Protocol-vorm nodig hebben — dat
  blijft een aparte afweging op het moment dat het zich voordoet.
