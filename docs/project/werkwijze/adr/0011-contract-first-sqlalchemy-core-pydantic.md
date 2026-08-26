# ADR-0011: Contract-first "de ene bron" — SQLAlchemy Core-tabel + Pydantic-model

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

`feature-bouwen` regel 3 noemt SQLAlchemy Core + Pydantic + `openapi-typescript` al als de
voorziene invulling voor deze werkwijze (`BACKLOG.md` §Core), maar liet in het midden hoe die
combinatie er concreet uitziet. Dat is niet triviaal over te slaan: in tegenstelling tot een ORM
waarin één class tegelijk tabel en contract kan zijn, zijn een SQLAlchemy Core `Table` en een
Pydantic-model twee aparte objecten die expliciet met elkaar verbonden moeten worden. Zonder een
vastgelegd patroon ontstaat per feature een andere aanpak.

## Beslissing

Per entiteit staan in hetzelfde `models.py`-bestand van de feature:

- een SQLAlchemy Core `Table`-definitie (de databasetabel);
- een of meer Pydantic-modellen (het contract: een Base met gedeelde velden, een Create-variant
  voor input, een Read-variant voor output);
- een expliciete, met de hand geschreven mapping-functie tussen een databaserij en het
  Pydantic-model — geen impliciete/automatische ORM-mapping.

De generatieketen (Pydantic-modellen → OpenAPI-schema → `openapi-typescript` → TypeScript-types)
heet `scripts/genereer-types.sh`, binnen elke service die een frontend bedient. Draai dit na
elke wijziging aan een `models.py`.

## Consequenties

- Vorm blijft op één plek (het `models.py` van de feature) ondanks dat Core en Pydantic twee
  aparte objecten zijn — de mapping-functie is de enige plek waar ze samenkomen.
- Geen impliciete ORM-laag die stilzwijgend gedrag toevoegt; expliciete mapping is meer
  typwerk, maar voorspelbaarder.
- Nadeel, bewust geaccepteerd: een velduitbreiding raakt drie plekken in hetzelfde bestand
  (`Table`, Pydantic-model, mapping-functie) in plaats van één class zoals bij een ORM die beide
  rollen combineert — geaccepteerd omdat SQLAlchemy Core bewust boven een ORM gekozen is
  (`BACKLOG.md`), en de expliciete mapping voorkomt dat databaselaag en API-contract stilzwijgend
  uit elkaar lopen.
- Dit is de vaste, methodologiebrede invulling van "de ene bron" voor deze werkwijze. Een
  project-specifiek `stack-profiel.md` (ADR-0004) hoeft dit patroon niet opnieuw te bedenken,
  alleen te bevestigen — of, in een uitzonderingsgeval, gemotiveerd af te wijken.
- Dit ADR maakt geen CI-afdwinging waar: `check-generated-types`-achtige verificatie hangt af
  van het nog openstaande "CI/CD per service"-backlogpunt.
