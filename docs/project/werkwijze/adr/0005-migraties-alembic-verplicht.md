# ADR-0005: Migraties — Alembic verplicht zodra een service een productiedatabase heeft

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een "maak ontbrekende tabellen aan bij opstarten"-mechanisme (zoals `create_all()`) maakt geen
`ALTER` en geen kolom-migratie op een bestaande tabel. Zonder migratietooling ontstaat daarom
al snel een handmatige schema-reconciliatiefunctie: één groeiende functie met losse
`ALTER TABLE`-statements, één per historische schemawijziging. Dat is een bekende faalmodus —
een kolomwijziging moet dan op twee plekken tegelijk correct blijven (het model, en de losse
`ALTER`-regel), en één vergeten plek is een bug die pas in productie opvalt.

## Beslissing

Zodra een service tegen een echte, persistente database draait, is Alembic (of het equivalent
voor de gekozen taal/ORM) verplicht. Geen handmatige schema-reconciliatiefunctie, geen losse
`ALTER`-statements in de opstartcode. Elke service heeft zijn eigen migratiemap en -historie —
gedeelde migratiehistorie tussen services bestaat niet, want elke service heeft zijn eigen
databaseproces (ADR-0002).

`create_all()` (of gelijkwaardig) blijft toegestaan zolang een service nog geen enkele
productiedata heeft — `feature-bouwen` regel 7 bepaalt het omslagpunt. Zodra dat punt gepasseerd
is, is teruggaan naar een schemaloos mechanisme niet de bedoeling.

## Consequenties

- Opstartcode blijft dun — geen schemalogica in de applicatie zelf.
- Elke schemawijziging is een los, review-baar migratiebestand, zelfstandig te testen en uit te
  voeren vóór een deploy.
- Nadeel, bewust geaccepteerd: meer ceremonie dan `create_all()` voor een service die nog in de
  prototype-fase zit. Dat is de prijs voor een schema-evolutie die niet stilzwijgend kan
  desynchroniseren van de code — voor een service zonder productiedata weegt dat nog niet op,
  daarna wel.
