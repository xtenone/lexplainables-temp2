# Stack-profiel — <projectnaam>

Wat dit project concreet gekozen heeft op de punten die de skills anders zouden aannemen (zie
ADR-0004). Kopieer dit bestand naar `docs/architectuur/stack-profiel.md` in het project en vul
elke sectie in vóórdat je `feature-bouwen` gebruikt. Een sectie leeglaten is geen neutrale keuze
— de skill die 'm nodig heeft, stopt dan en vraagt erom.

Dit bestand legt vast *wat* er gekozen is, niet *waarom*. Een keuze met een echte afweging en
nadelen hoort daarnaast in een eigen ADR in het project.

## Topologie

Welke services bestaan er, hoe heten ze, in welke map staan ze, en waar is elke service
verantwoordelijk voor? Meerdere, onafhankelijk deploybare services is het uitgangspunt
(ADR-0002); noem ze hier expliciet op, want `feature-bouwen` regel 2 kiest hieruit.

Noem er ook bij hoe ze onderling communiceren (synchroon HTTP, events, of allebei) en welke
service welke database bezit.

| Service | Map | Verantwoordelijk voor | Praat met |
|---|---|---|---|
| | | | |

## De ene bron

Waar staat de vorm (velden, types) van een entiteit binnen een service, in precies één
definitie? Noem het bestand of de conventie, en hoe het contract voor de buitenwereld daaruit
volgt (`feature-bouwen` regel 3).

## Contractgeneratie

Ja of nee. Zo ja: welk script, welke invoer, welke bestanden schrijft het, en waar staat de
uitvoer (`feature-bouwen` regel 4)? Zo nee: hoe wordt het contract dan wél op één plek
gehouden?

Noem ook hoe het contract *tussen* twee services vastligt en geversioneerd wordt — dat is een
ander mechanisme dan de generatie binnen een service (ADR-0002).

## Feature-eenheid

Hoe heet een feature-map binnen een service, en welke bestanden horen erin (schema, routes,
tests)? Dit is wat `feature-bouwen` regel 2 aanmaakt en wat `architectuur-audit` regel 1 leest.

## Dunne verzamelaars

Welke bestanden per service zijn samenvoegers zonder domeinkennis (het routes-samenvoegpunt, de
database-setup)? `architectuur-audit` regel 3 bewaakt precies deze lijst op ongewenste groei.

## Migraties

Hoe komt een schemawijziging in een bestaande database terecht (`feature-bouwen` regel 7)? Noem
het gereedschap, waar de migraties staan, en wie ze uitvoert bij een deploy.

## Frontend(s)

Welke frontend-apps zijn er, waar staan ze, en welke hoort bij welke service(s)
(`frontend-bouwen` regel 1)? Noem per frontend de map met de gegenereerde types en de map met
de E2E-tests.

## Codestandaard

De exacte lint- en formatconfiguratie per taal, en waar die config staat (`CLAUDE.md`
§Codestandaard, ADR-0003). Noem ook de namen van de CI-checks die dit afdwingen.
