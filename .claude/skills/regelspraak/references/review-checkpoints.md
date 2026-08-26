# Review-checkpoints — datacontract en werkwijze

Na het opstellen van GegevensSpraak (stap 2) en van de RegelSpraak-regels (stap 3) pauzeert de skill
voor een review door de analist (human-in-the-loop). Dit bestand beschrijft hoe je het tussenresultaat
wegschrijft, de review-server start en de feedback verwerkt. De aanpak spiegelt die van de
`wetsanalyse`-skill.

Waarom: formaliseren is multidisciplinair werk. De vertaling naar GegevensSpraak/RegelSpraak — en zeker
de interpretatiekeuzes — moeten door mensen (jurist, informatieanalist, ICT) worden gevalideerd vóór de
specificatie de uitvoering in gaat. De review-momenten maken die validatie expliciet en traceerbaar.

## De eenheid: het werkgebied

De analyse-eenheid is het **werkgebied** (overgenomen uit de wetsanalyse, of bij het standalone-pad
zelf bepaald): een afbakening die zich over één of meer bronnen (`bwbId`, artikel, lid) uitstrekt. Elke
declaratie en regel draagt een **`herkomst`** met `vindplaatsen: [{bron_id, lid}]` zodat de bron
herleidbaar blijft. **Id's zijn werkgebied-breed uniek** (`ot1..`, `rs1..`) en stabiel tussen rondes —
daarop koppelt de feedback terug.

## Werkmap — één map per ronde

De review is **iteratief**: na elke ronde feedback verwerk je en toon je het herziene resultaat
opnieuw. Bewaar de volledige historie — overschrijf niets. De werkmap ligt onder de analysemap:

```
analyses/<werkgebied-slug>/regelspraak/
  werk/
    gegevensspraak/
      ronde-1/  model.json  feedback.json
      ronde-2/  model.json  feedback.json
      ...
    regels/
      ronde-1/  model.json  feedback.json
      ...
  model.json            # eindresultaat (build_regelspraak.py)
  model.rs / model.md   # RegelSpraak-tekstexport (via de viewer)
```

- `ronde-N/model.json` — tussenresultaat van die ronde (jij schrijft dit).
- `ronde-N/feedback.json` — feedback van de analist op die ronde (de viewer schrijft dit).

De `<werkgebied-slug>` leid je af van de werkgebied-naam (kebab-case); bij ontbreken val je terug op de
eerste bron (`<bwbid>-art<nr>[-lidN]`). Bestaat er al een wetsanalyse-map voor dit werkgebied, plaats de
`regelspraak/`-submap daar dan in.

## Schema — `model.json` (stap GegevensSpraak)

```json
{
  "werkgebied": {
    "naam": "Treinmiles op korte afstand",
    "scoping": "<welke artikelen/leden in scope; bron_rapport indien gebruikt>",
    "bron_rapport": "analyses/<werkgebied>/rapport.json"
  },
  "gegevensspraak": {
    "eenheidssystemen": [
      { "naam": "Valuta", "regelspraak_tekst": "Eenheidssysteem Valuta\n  de euro (mv: euros) EUR €" }
    ],
    "domeinen": [
      { "naam": "Bedrag", "regelspraak_tekst": "Domein Bedrag is van het type Numeriek (getal met 2 decimalen) met eenheid €" }
    ],
    "objecttypen": [
      {
        "id": "ot1",
        "naam": "Natuurlijk persoon",
        "lidwoord": "de",
        "meervoud": "Natuurlijke personen",
        "bezield": true,
        "attributen": [
          { "naam": "leeftijd", "lidwoord": "de", "datatype": "Numeriek (niet-negatief geheel getal)", "eenheid": "jr" }
        ],
        "kenmerken": [
          { "naam": "minderjarig", "soort": "bijvoeglijk" }
        ],
        "regelspraak_tekst": "Objecttype de Natuurlijk persoon (mv: Natuurlijke personen) (bezield)\n  de leeftijd  Numeriek (niet-negatief geheel getal) met eenheid jr;\n  is minderjarig  kenmerk (bijvoeglijk);",
        "herkomst": { "begrip_ids": ["b3"], "vindplaatsen": [{ "bron_id": "br1", "lid": "1" }] },
        "twijfel": ""
      }
    ],
    "feittypen": [
      {
        "id": "ft1",
        "naam": "Vlucht van natuurlijke personen",
        "wederkerig": false,
        "rollen": [
          { "naam": "reis", "lidwoord": "de", "objecttype": "Vlucht", "multipliciteit": "een" },
          { "naam": "passagier", "objecttype": "Natuurlijk persoon", "multipliciteit": "meerdere" }
        ],
        "relatiebeschrijving": "betreft de verplaatsing van",
        "regelspraak_tekst": "Feittype Vlucht van natuurlijke personen\n  de reis  Vlucht\n  de passagier  Natuurlijk persoon\nEén reis betreft de verplaatsing van meerdere passagiers",
        "herkomst": { "begrip_ids": ["b8"], "vindplaatsen": [{ "bron_id": "br1", "lid": "2" }] }
      }
    ],
    "parameters": [
      {
        "id": "par1", "naam": "volwassenleeftijd", "lidwoord": "de",
        "datatype": "Numeriek (niet-negatief geheel getal)", "eenheid": "jr",
        "regelspraak_tekst": "Parameter de volwassenleeftijd : Numeriek (niet-negatief geheel getal) met eenheid jr",
        "herkomst": { "begrip_ids": ["b5"], "vindplaatsen": [{ "bron_id": "br1", "lid": "1" }] }
      }
    ],
    "dimensies": [], "tijdlijnen": [], "dagsoorten": []
  }
}
```

- Elke declaratie draagt een **`regelspraak_tekst`** (de letterlijke GegevensSpraak) én een
  **`herkomst`** (`begrip_ids` + `vindplaatsen`). De gestructureerde velden (objecttypen/attributen/…)
  voeden de mechanische validatie; de `regelspraak_tekst` voedt de viewer en de `.rs`-export.
- `kenmerk.soort` ∈ `bijvoeglijk | bezittelijk | overig`. `rol.multipliciteit` ∈ `een | meerdere`.
- `twijfel` is optioneel: leg interpretatiekeuzes vast (komt later bij de validatiepunten).

## Schema — `model.json` (stap regels)

```json
{
  "werkgebied": { "naam": "...", "scoping": "...", "bron_rapport": "..." },
  "gegevensspraak_index": {
    "objecttypen": [{ "id": "ot1", "naam": "Natuurlijk persoon" }],
    "parameters":  [{ "id": "par1", "naam": "volwassenleeftijd" }],
    "feittypen":   [{ "id": "ft1", "naam": "Vlucht van natuurlijke personen", "rollen": ["reis", "passagier"] }]
  },
  "regels": [
    {
      "id": "rs1",
      "naam": "Kenmerktoekenning persoon minderjarig",
      "soort": "kenmerktoekenning",
      "regelspraak_tekst": "Regel Kenmerktoekenning persoon minderjarig\n  geldig altijd\n    Een Natuurlijk persoon is minderjarig\n    indien zijn leeftijd kleiner is dan de volwassenleeftijd.",
      "herkomst": { "regel_id": "r1", "vindplaatsen": [{ "bron_id": "br1", "lid": "1" }] },
      "twijfel": ""
    }
  ],
  "validatiepunten": ["<aandachtspunt 1>"]
}
```

De `gegevensspraak_index` is een **lichte index** (`id` → leesbare `naam`) zodat de regel-review
zelfstandig leesbaar is en de validatie kan toetsen of verwezen objecttypen/rollen/parameters bestaan.
`regel.soort` ∈ `gelijkstelling | kenmerktoekenning | consistentieregel | initialisatie | objectcreatie
| feitcreatie | verdeling | dagsoortdefinitie | startpuntbepaling`.

## De server starten

Stap GegevensSpraak, ronde 1:
```bash
python "<skill>/scripts/review_server.py" \
  --input "regelspraak/werk/gegevensspraak/ronde-1/model.json" \
  --stap gegevensspraak \
  --feedback-out "regelspraak/werk/gegevensspraak/ronde-1/feedback.json" \
  --ronde 1
```
Ronde 2+: voeg `--ronde {N}` en `--vorige regelspraak/werk/gegevensspraak/ronde-{N-1}` toe (de server
toont dan per item de vorige feedback en de vorige versie). De stap `regels` werkt identiek met
`--stap regels` en de `regels/`-werkmap.

Default poort **3120**. Start in de achtergrond, geef de analist de URL (`http://localhost:3120`), en
**pauzeer**: rond je beurt af met een duidelijke instructie ("Bekijk de review, geef desgewenst
feedback en klik op de verstuurknop (leeg = akkoord), en laat het me weten als je klaar bent"). Ga
niet zelf door tot de analist bevestigt.

## Schema — `feedback.json` (door de viewer geschreven, per ronde)

```json
{
  "status": "akkoord",
  "stap": "gegevensspraak",
  "items": { "ot1": "Maak 'leeftijd' niet-negatief.", "rs1": "Voeg een geldigheidsperiode toe." },
  "algemeen": "Objecttype 'Vlucht' ontbreekt nog."
}
```
`status` ∈ `akkoord | wijzigingen`. Een `items`-sleutel is een declaratie- of regel-`id`. Houd id's
**stabiel tussen rondes**: hetzelfde concept houdt hetzelfde id, ook na een correctie.

## De iteratieve lus

1. **Schrijf** `ronde-{N}/model.json` en draai de pre-check
   (`validate_regelspraak.py --stap <stap>`). Werk je vanuit een wetsanalyse-rapport, geef dan ook
   `--ingest <pad>/regelspraak/werk/ingest.json` mee: de pre-check toetst dan de **herkomst-keten**
   tegen de wetsanalyse. Twee richtingen:
   - **integriteit (blokkerend, exit 2):** een `herkomst.begrip_ids`/`regel_id` of een
     `vindplaatsen.bron_id` die niet in de ingest voorkomt = dangling herkomst → herstel het
     (verkeerd of verschoven id) vóór de review.
   - **dekking (waarschuwing, exit 1):** een ingest-begrip (stap gegevensspraak) of -afleidingsregel
     (stap regels) dat door geen enkele declaratie/regel wordt geraakt → dek het alsnog, of zet het
     bewust buiten scope bij de validatiepunten.

   Zonder `--ingest` (standalone-pad) blijft de pre-check ongewijzigd. Start daarna de server
   (ronde 1 zonder `--vorige`, ronde 2+ met `--vorige ronde-{N-1}` en `--ronde N`).
2. **Pauzeer** en wacht tot de analist bevestigt dat die klaar is.
3. **Lees** `ronde-{N}/feedback.json`.
   - `status: "akkoord"` **zonder** `items` en **zonder** `algemeen`: de lus is klaar. Stop de server en
     ga door (naar de regels, of naar het model).
   - Anders: verwerk **elk** gevuld veld (per `id` de declaratie/regel aanpassen; `algemeen` kan items
     toevoegen/verwijderen of methodisch sturen). Stop de server, verhoog `N`, ga terug naar stap 1.
4. **Veiligheidscap:** stop na maximaal **6 rondes**, ook als er nog feedback is. Meld dit en noteer de
   resterende punten bij de validatiepunten.

Houd per ronde bij wat je wijzigde; dat komt in de **reviewlogs** van het eindmodel.

## Niet-interactief draaien (alleen voor evals/automatisering)

Bij `REGELSPRAAK_NO_REVIEW=1` in de omgeving sla je de hele lus over: schrijf één keer
`ronde-1/model.json` (geen server, geen pauze) en noteer in het eindmodel dat de reviews zijn
overgeslagen. Gebruik dit uitsluitend voor geautomatiseerde tests; voor mensen blijven de checkpoints
altijd aan.
