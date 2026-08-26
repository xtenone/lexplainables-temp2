---
name: implementatieplan
description: >-
  Vertaalt een goedgekeurde user story naar een concreet implementatieplan vóór er code
  geschreven wordt: welke bestanden aanmaken of aanpassen, welke migratie, welke
  Pydantic-modellen, welke endpoints, welke testcases — en vraagt de gebruiker om goedkeuring
  via plan mode. Slaat het goedgekeurde plan op in de story-doc als naslagwerk voor
  `feature-bouwen` en `code-review`. Gebruik deze skill na `story-review` (en na
  `frontend-bouwen fase 1` als de story een UI heeft), vóór `feature-bouwen`, bij stories van
  3+ story points of als meerdere bestanden/services geraakt worden. Bij eenvoudige 1-2 SP uitbreidingen (één endpoint, geen migratie) mag deze stap
  worden overgeslagen — maar twijfel je, gebruik hem dan.
---

# Implementatieplan — brug tussen story en code

**Trigger:** na `story-review` (en na `frontend-bouwen fase 1` als de story een UI heeft),
vóór `feature-bouwen` begint. Gebruik bij 3+ SP of meerdere geraakte bestanden. Optioneel bij
1-2 SP.

**Doel:** zichtbaar maken *hoe* de story gebouwd wordt — zodat de gebruiker kan bijsturen
vóórdat er code bestaat, en er een naslagwerk is tijdens `code-review`.

## Stappen

### 1. Lees de context

Lees, in deze volgorde:
- De story-doc (`docs/stories/<nr>-<naam>.md`) — volledig
- `docs/architectuur/stack-profiel.md` — §Feature-eenheid, §De ene bron, §Migraties,
  §Topologie, §Contractgeneratie
- `CLAUDE.md` van de betreffende service — build/test-commando's, instellingen
- De bestaande feature-mappen die het dichtst bij de nieuwe story liggen (één of twee) — als
  referentie voor het patroon, niet om te kopiëren

### 2. Stel het plan op in plan mode

Roep `EnterPlanMode` aan en schrijf het plan. Het plan bevat:

**Nieuwe bestanden (aanmaken):**
Lijst elk nieuw bestand met pad en een zin over wat het bevat.
Voorbeeld:
- `api/app/features/api_tokens/models.py` — SQLAlchemy Core `Table` + Pydantic `ApiTokenRead`, `ApiTokenAangemaakt`, `ApiTokenAanmakenVerzoek`
- `api/alembic/versions/0010_api_tokens.py` — Alembic-migratie: tabel `api_tokens`

**Bestaande bestanden (aanpassen):**
Lijst elk bestand dat gewijzigd wordt met een zin over de wijziging.
Voorbeeld:
- `api/app/shared/auth.py` — `vereist_api_token` uitbreiden met DB-token-verificatielaag
- `api/app/main.py` — router registreren

**Schema (tabel + modellen):**
Herhaal de kerntypes beknopt — kolommen, Pydantic-velden, endpoints met methode + pad + auth.
Dit is geen volledige schemabeslissing (die staat al in de story), maar een compacte samenvatting
voor tijdens de bouw.

**Testcases (gedrag):**
Lijst de gedragstests die `feature-bouwen` regel 6 gaat schrijven — per acceptatiecriterium
minstens één test. Noem randgevallen expliciet (404, 409, lege lijst, etc.).

**Afhankelijkheden en aandachtspunten:**
Alles wat afwijkt van het standaardpatroon: migratienummer (check de hoogste bestaande migratie),
gedeelde logica (welk bestaand bestand uitgebreid wordt), async-noodzaak, etc.

### 3. Wacht op goedkeuring

`ExitPlanMode` vraagt de gebruiker om goedkeuring. De gebruiker kan:
- **Akkoord gaan** → door naar stap 4
- **Bijsturen** → pas het plan aan en herhaal stap 2-3
- **Afwijzen** → stop; overleg met de gebruiker wat er mis is

### 4. Sla het plan op

Voeg het goedgekeurde plan toe aan de story-doc als `## Implementatieplan`-sectie, direct voor
`**Gebouwd:**`. Schrijf het als een geordende lijst (geen proza), zodat het snel te scannen is
tijdens `code-review`.

Formaat:

```markdown
## Implementatieplan

**Nieuwe bestanden:**
- `pad/naar/bestand.py` — korte omschrijving

**Aangepaste bestanden:**
- `pad/naar/bestand.py` — wat er verandert

**Migratie:** `0010_api_tokens.py` — tabel `api_tokens`

**Endpoints:**
- `GET /v1/admin/api-tokens` — lijst actieve tokens (beheerder)
- `POST /v1/admin/api-tokens` — nieuw token aanmaken (beheerder)
- `DELETE /v1/admin/api-tokens/{id}` — token intrekken (beheerder)

**Testcases:**
- aanmaken → token eenmalig in response, niet in lijst
- lijst → prefix zichtbaar, hash nooit
- intrekken → 204; daarna 404
- DB-token in auth-laag → 200; ongeldig token → 401
```

### 5. Geef overdracht aan feature-bouwen

Sluit af met: "Plan opgeslagen in `docs/stories/<nr>-<naam>.md`. Klaar voor `feature-bouwen`."

`feature-bouwen` leest het plan als context bij stap 1 (schemabeslissing) — het plan vervangt
die stap niet, maar maakt hem sneller: de beslissingen zijn al genomen.

## Wat dit niet is

- **Geen code schrijven** — dit is uitsluitend plannen. De eerste regel code schrijft
  `feature-bouwen`.
- **Geen volledige schemabeslissing herhalen** — die staat in de story-doc. Het plan is een
  compacte implementatiesamenvatting, geen tweede story.
- **Geen ontwerp van toekomstige features** — alleen wat deze story vraagt.
