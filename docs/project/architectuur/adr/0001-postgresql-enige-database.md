# ADR-0001: PostgreSQL — enige database, ook in tests

**Status:** geaccepteerd
**Datum:** 2026-08-26

## Context

Werkwijze-ADR-0007 (`docs/project/werkwijze/adr/0007-store-abstractie-protocol-gebaseerd.md`)
laat de DB-keuze per omgeving open en noemt als voorbeeld "SQLite in tests, Postgres in
productie" — de Store-abstractie (Protocol per domein) maakt dat mogelijk, maar schrijft het
niet voor.

Voor dit project is die keuze al eerder gemaakt in het zusterproject `lexplainables`
(`docs/project/architectuur/adr/0003-postgresql-productie-sqlite-tests.md`): daar bleek
"Postgres productie, SQLite tests" binnen één dag drie latente bugs op te leveren zodra een
echte Postgres-CI-matrix draaide (naive datetime op `timestamptz`-kolommen,
boolean-server-defaults) — precies het soort verschil dat SQLite niet laat zien. Twee
SQL-dialecten onderhouden kost bovendien iedere feature een extra afweging, voor een
doelgroep die operationeel toch alleen Postgres kent.

## Beslissing

**PostgreSQL is de enige database in dit project — ook in tests.** Geen SQLite/`aiosqlite`,
in geen enkele service. Dit is een projectspecifieke aanscherping van werkwijze-ADR-0007: de
Store-abstractie (Protocol per domein) blijft van kracht, alleen de "lichte SQLite-implementatie
voor tests" uit die ADR vervalt hier — de testimplementatie van elk Protocol praat ook tegen
Postgres (testcontainer of lokale/CI Postgres-service), niet tegen SQLite.

Concreet, per service:
- Driver: `asyncpg` (runtime, via SQLAlchemy async), `psycopg2-binary` (Alembic sync-migraties).
- CI: één Postgres-service per relevante testjob.
- Lokaal draaien: `docker compose up -d postgres`, dan de test-DB-url naar die instance wijzen.
- Test-schema-reset per test (`metadata.drop_all` → `metadata.create_all` of een vergelijkbare
  testcontainer-helper), met `NullPool` om verbindingsuitputting te voorkomen bij een grotere
  testsuite.

## Consequenties

- **Bewust geaccepteerd:** ontwikkelaars hebben Docker (of een lokale Postgres) nodig om tests
  te draaien — geen echte drempel gegeven de al aanwezige docker-compose-tooling.
- **Winst:** één set SQL-patronen; een bug die zich alleen op Postgres manifesteert,
  manifesteert zich ook in tests/CI. Geen valse zekerheid via "SQLite is groen, dus goed".
- **Postgres-specifieke features** (JSONB, `SELECT FOR UPDATE SKIP LOCKED`, advisory locks,
  partial indexes) mogen zonder omweg gebruikt worden — geen dialect-agnostische SQL nodig.
- **Testrun iets langzamer** dan in-memory SQLite; gecompenseerd door `NullPool` en
  testcontainer-hergebruik waar mogelijk.
