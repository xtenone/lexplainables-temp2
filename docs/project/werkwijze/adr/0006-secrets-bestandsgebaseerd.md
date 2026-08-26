# ADR-0006: Secrets — bestandsgebaseerd, geen geheime waarden in env-vars

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Een geheim (API-key, wachtwoord, token) kan als losse env-var-waarde doorgegeven worden, of als
bestand waarvan alleen het pad in een env-var staat. De eerste vorm lekt makkelijker — env-vars
zijn zichtbaar in procesinfo (`/proc/<pid>/environ`), `docker inspect`, en soms in crash-dumps
of logging — en is lastig te roteren zonder het hele proces met een nieuwe env-var te
herstarten.

## Beslissing

Elk geheim wordt als bestand aangeleverd; de env-var bevat uitsluitend het pad naar dat bestand,
met de naamconventie `<NAAM>_FILE` (bijvoorbeeld `DATABASE_PASSWORD_FILE=/run/secrets/db_password`).
Applicatiecode leest het bestand bij opstart (of bij rotatie, als dat ondersteund wordt) —
nooit de geheime waarde rechtstreeks uit een env-var.

## Consequenties

- Werkt native met Docker/Compose-secrets en de meeste orchestrators, zonder extra tooling.
- Geheimen zijn nooit zichtbaar in procesomgeving of `docker inspect` — alleen het pad.
- Nadeel, bewust geaccepteerd: lokale ontwikkeling vraagt een lichte wrapper (secret-bestanden
  aanmaken in een genegeerde map) in plaats van gewoon een waarde in `.env` zetten — iets meer
  frictie voor een consistent patroon tussen lokaal en productie.
