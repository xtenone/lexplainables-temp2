# Verwijzingen inventariseren en volgen (stap 1b)

Wetsformuleringen verwijzen voortdurend naar andere bepalingen: naar het definitieartikel
vooraan ("in deze wet wordt verstaan onder…"), naar andere leden ("in afwijking van het
eerste lid"), naar schakelbepalingen ("van overeenkomstige toepassing"), en naar
gedelegeerde regelingen (amvb / ministeriële regeling). Die verwijzingen bepalen mede de
*betekenis* en *werking* van de bepaling die je analyseert. Deze stap maakt ze expliciet,
volgt de relevante, en legt ze traceerbaar vast als `verwijzingen`-array **op de bron** in
`analyse.json` (elke verwijzing draagt het `bron_id` van haar bron).

`verwijzingen` is een **aparte as** náást de markeringen: het zijn uitgaande pointers van de
bepaling, géén tweede plek om JAS-klassen te registreren. Een delegatie blijft óók een
markering met klasse *Delegatiebevoegdheid en delegatie-invulling*, en is daarnaast een
verwijzing met functie *delegatie*. Een hergebruikte brondefinitie blijft een begrip met de
brondefinitie als definitie, en wijst met `bron_verwijzing` naar de definitie-verwijzing.

## Twee herkomsten

1. **Getagde verwijzingen** — `wettenbank_artikel` geeft per lid een `verwijzingen`-array
   (intref/extref) met `target`, `label`, `bwbIdDoel` en `extern`. Deze staan óók als
   inline-Markdown-link in de `tekst`. Neem ze over.
2. **Natuurlijke-taalverwijzingen** — verwijzingen zonder XML-tag die de MCP niet vangt, bv.
   "in afwijking van het eerste lid", "van overeenkomstige toepassing", "de in artikel 5
   bedoelde termijn". Herken die zelf in de letterlijke tekst en noteer ze met `soort:
   "natuurlijk"` (vaak alleen een `doel.label`, geen `target`).

## Classificeer naar functie

| Functie | Wat het is | Herken aan |
| --- | --- | --- |
| **definitie** | Verwijst naar een begripsomschrijving die de betekenis bepaalt | "in deze wet wordt verstaan onder", verwijzing naar het definitieartikel |
| **schakel** | Maakt een andere bepaling (deels) van toepassing of wijkt ervan af | "van overeenkomstige toepassing", "in afwijking van", "onverminderd" |
| **delegatie** | Verwijst naar een lagere regeling die nadere regels stelt | "bij of krachtens algemene maatregel van bestuur", "bij ministeriële regeling" |
| **intra-artikel** | Verwijst naar een ander lid van hetzelfde artikel | "het eerste lid", "het bepaalde in het tweede lid" |
| **informatief** | Verwijst zonder de betekenis/werking te raken | losse signalering, "zie ook" |

## Volg-beleid (default)

| Functie | Default actie | Diepte | Tool |
| --- | --- | --- | --- |
| **definitie** | Ophalen; de definitie letterlijk hergebruiken in het begrip (`bron_verwijzing`) | 1 | `wettenbank_zoekterm` / `wettenbank_artikel` |
| **schakel** | Ophalen voor zover het de focus-bepaling betekenis geeft | 1 | `wettenbank_artikel` |
| **delegatie** | *Bounded:* vindplaats + relevante bepaling identificeren, de betekenis verwerken. Wordt de gedelegeerde regeling relevant genoeg, **promoveer haar tot een eigen bron** in het werkgebied (het werkgebied mag groeien); anders signaleer je een volledige JAS-analyse als validatiepunt | 1 (identificatie) | `wettenbank_structuur` |
| **intra-artikel** | Als relatie vastleggen; de tekst staat al in scope | 0 | — |
| **informatief** | Signaleren, niet volgen | — | — |

## Grenzen tegen scope-explosie

Omdat alle soorten in beginsel gevolgd worden, gelden twee harde grenzen:

- **Diepte-cap = 1.** Volg verwijzingen één niveau vanaf de focus-bepaling. Een verwijzing
  *ván* een verwezen artikel volg je niet automatisch verder: noteer haar met status
  `buiten-scope-diepte`. De analist kan in het checkpoint vragen dieper te gaan.
- **Relevantie-gate.** Haal een verwijzing alleen daadwerkelijk op als ze de *betekenis of
  werking van de focus-bepaling* raakt. Louter informatieve verwijzingen krijgen status
  `gesignaleerd`. Elke gevolgde verwijzing is bovendien een extra, trage `overheid.nl`-call —
  houd het gericht.

## Status per verwijzing

- `opgehaald` — gevolgd én de tekst opgehaald (de betekenis is in de analyse verwerkt).
- `gevolgd` — gevolgd zonder aparte fetch (bv. intra-artikel: de tekst is al in scope).
- `gesignaleerd` — herkend maar bewust niet gevolgd (informatief of niet-relevant).
- `buiten-scope-diepte` — buiten de diepte-cap gelaten; kandidaat om als bron toe te voegen.

## Registreren

Schrijf de verwijzingen als `verwijzingen`-array **op de betreffende bron** in
`werk/activiteit-2/ronde-{N}/analyse.json` (zie het schema in
`references/review-checkpoints.md`), met **werkgebied-breed stabiele id's** (`v1`, `v2`, …) en
het `bron_id` van de bron. `validate_analyse.py` controleert de structuur (functie/status-enums,
`doel.label`, id-uniciteit over bronnen, en de delegatie-koppeling); `build_rapport_json.py`
controleert of elke `bron_verwijzing` op een begrip/regel naar een bestaande verwijzing in één
van de bronnen wijst.

**Houd stap 1b licht:** het is inventariseren + gericht ophalen, niet al classificeren in
JAS-klassen — dat blijft activiteit 2. De verwijzing-inventaris hoort bij het activiteit-2
review-checkpoint, zodat de analist de scope kan bijsturen.
