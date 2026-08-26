# Review-checkpoints — datacontract en werkwijze

Na activiteit 2 pauzeert de skill voor een review door de analist
(human-in-the-loop). Dit bestand beschrijft hoe je het tussenresultaat wegschrijft, de
review-server start, en de feedback verwerkt.

> **Scope.** De skill dekt op dit moment **activiteit 2**. Activiteit 3 (begrippen +
> afleidingsregels) en de RegelSpraak-vervolgstap zijn uit scope — ze worden later op een
> agentische basis opnieuw opgebouwd.

Waarom: Wetsanalyse is een multidisciplinaire, iteratieve methode. De betekenis van
wetgeving — en zeker de interpretatiekeuzes — moeten door mensen (jurist,
informatieanalist, ICT) worden gevalideerd vóórdat de analyse de uitvoering in gaat. De
review-momenten maken die validatie expliciet en traceerbaar.

## De analyse-eenheid: het werkgebied (met meerdere bronnen)

De analyse-eenheid is het **werkgebied** (stap 1 "Bepalen van het werkgebied"; in WetsTaal
*kennisdomein*): een afbakening die zich over **meerdere bronnen** uitstrekt — leden,
artikelen, hoofdstukken, en zelfs meerdere regelingen (bv. een wet + de gedelegeerde
regeling). Eén **bron** is één `(bwbId, artikel, lid?)`-eenheid ("tekstdeel").

- **Activiteit 2** wordt per bron uitgevoerd (markeren/classificeren + uitgaande
  verwijzingen) en in één `analyse.json` met een `bronnen`-array geaggregeerd.

Een werkgebied met één bron is het triviale geval (`bronnen` met één element).

**Id's zijn werkgebied-breed uniek** (`m1..mN` voor markeringen, `v1..` voor verwijzingen) — vergelijkbaar met
de kennisdomein-brede identificatie in WetsTaal (RS01/RB01). Elke markering/verwijzing draagt
daarnaast een expliciet **`bron_id`** zodat de bron herleidbaar blijft, ook nadat de viewer de
items afvlakt. De feedback koppelt op die id's terug; houd ze stabiel tussen rondes.

## Werkmap — één map per ronde

De review is **iteratief**: na elke ronde feedback verwerk je en toon je het herziene
resultaat opnieuw. Bewaar daarom de volledige historie — overschrijf niets. Schrijf naar
een werkmap bij het eindrapport (`werk/`), met per activiteit een submap en daarin per
ronde een map met twee vaste bestanden:

```
analyses/<werkgebied-slug>/
  werk/
    activiteit-2/
      ronde-1/  analyse.json  feedback.json   # bevat bronnen[]
      ronde-2/  analyse.json  feedback.json
      ...
  rapport.json
```

- `ronde-N/analyse.json` — tussenresultaat van die ronde (jij schrijft dit).
- `ronde-N/feedback.json` — feedback van de analist op die ronde (de viewer schrijft dit).

De `<werkgebied-slug>` leid je af van de werkgebied-naam (kebab-case); bij ontbreken val je
terug op de eerste bron (`<bwbid>-art<nr>[-lidN]`).

Het auditspoor laat zo zien hoe de analyse onder de feedback van de analist evolueerde —
dat past bij de traceerbaarheidseis van het project.

## Schema — `analyse.json` (activiteit 2)

```json
{
  "werkgebied": {
    "naam": "Inkomensafhankelijke bijdrage Zvw",
    "hoofdvraag": "Het berekenen van de inkomensafhankelijke bijdrage Zvw",
    "omschrijving": "<korte omschrijving van de casus>",
    "scoping": "<welke hoofdstukken/artikelen overwogen; wat in/uit scope is en waarom>"
  },
  "analysefocus": "<hoofdvraag, of weglaten voor volledige analyse>",
  "bronnen": [
    {
      "bron_id": "br1",
      "label": "Zvw art. 43 lid 2",
      "wet": "Zorgverzekeringswet",
      "bwbId": "BWBR0018450",
      "artikel": "43",
      "lid": "2",
      "versiedatum": "2026-01-01",
      "bronreferentie": "jci1.3:c:BWBR0018450&artikel=43&lid=2",
      "type": "wet",
      "pad": "Hoofdstuk 5 > Paragraaf 5.2 > Artikel 43",
      "reikwijdte": "<welke leden zijn geanalyseerd; wat valt buiten scope>",
      "geraadpleegde": "<definitie-/aanpalende artikelen, bv. art. 1 (begripsbepalingen)>",
      "leden": [{ "lid": "2", "tekst": "<letterlijke wettekst van het lid>" }],
      "markeringen": [
        {
          "id": "m1",
          "bron_id": "br1",
          "formulering": "<letterlijke formulering>",
          "klasse": "Rechtssubject",
          "vindplaats": "lid 2",
          "toelichting": "<waarom deze klasse; evt. alternatief>"
        }
      ],
      "verwijzingen": [
        {
          "id": "v1",
          "bron_id": "br1",
          "bron_lid": "lid 2",
          "soort": "intref",
          "functie": "definitie",
          "doel": { "label": "artikel 1, onder e", "target": "jci1.3:c:BWBR0018450&artikel=1", "bwbId": "BWBR0018450" },
          "status": "opgehaald",
          "betekenis": "<wat de verwijzing toevoegt aan de bepaling>"
        }
      ],
      "samenhang": "<korte tekst over samenhang rond rechtsbetrekking/rechtsfeit>"
    }
  ]
}
```

Elke bron draagt de brongetrouwe metadata (`wet`, `bwbId`, `artikel`, `lid`, `versiedatum`,
`bronreferentie`, `type`, `pad`) plus zijn `leden`, `markeringen`, `verwijzingen` en
`samenhang`. `markering.vindplaats` is **lid-relatief** (`"lid 2"`) — de bron staat in
`bron_id`.

Het veld **`verwijzingen`** legt de uitgaande verwijzingen van een bron vast — zie
`references/verwijzingen-volgen.md` voor de werkwijze en het beleid. Het is een aparte as
náást de markeringen (uitgaande pointers, geen tweede registratie van JAS-klassen).
`functie` ∈ `definitie | schakel | delegatie | intra-artikel | informatief`; `status` ∈
`opgehaald | gevolgd | gesignaleerd | buiten-scope-diepte`; `soort` ∈
`intref | extref | natuurlijk` (`natuurlijk` = natuurlijke-taalverwijzing die de MCP niet
tagt, bv. "het eerste lid"). `doel.label` is verplicht; `target`/`bwbId` alleen indien bekend.

**Dienst-spoor-uitbreidingen van het contract.** De API/webapp voegt aan hetzelfde schema een
paar velden toe die het skill-spoor niet hoeft te schrijven maar wel kan tegenkomen (bv. bij
het inlezen van een API-rapport):
- `verwijzing.volgen` (bool) — het scope-besluit uit de inventaris-stap: haalt de begrensde
  fetch-lus deze verwijzing op? (In het skill-spoor drukt `status` dat besluit uit.)
- `markering.twijfel` (string) — expliciete twijfel/aanname bij een markering, naast
  `toelichting`.
- `lid.bronreferentie` (string) — jci-uri op lid-niveau in `leden[]`, naast de
  bron-brede `bronreferentie`.
Volg je een definitie/delegatie en wordt die zelf relevant genoeg om te markeren, dan
**promoveer** je haar tot een eigen bron in het werkgebied (het werkgebied mág groeien).

De werkgebied-velden (`naam`, `hoofdvraag`, `omschrijving`, `scoping`) en de per-bron-velden
`type`, `pad`, `reikwijdte`, `geraadpleegde` voeden sectie 0 (Bron en afbakening) van het
eindrapport. `pad`/`type` komen uit `wettenbank_artikel` / `wettenbank_structuur`;
`scoping`/`reikwijdte`/`geraadpleegde` leg je vast uit de opdracht en je afbakening. Ze zijn
optioneel: ontbreken ze, dan geeft `build_rapport_json.py` ze als lege string door aan
`rapport.json`, waarna je ze in de HTML-viewer (de §3-velden van `rapport_server.py`) bijstelt.

## De server starten

Ronde 1 (geen vorige context):

```bash
python "<skill>/scripts/review_server.py" \
  --input "<werkmap>/activiteit-2/ronde-1/analyse.json" \
  --activiteit 2 \
  --feedback-out "<werkmap>/activiteit-2/ronde-1/feedback.json" \
  --ronde 1
```

Ronde 2 en verder: geef met `--vorige` de map van de vorige ronde mee. De server laadt
dan `analyse.json` en `feedback.json` van die ronde en toont per item wat de analist toen
vroeg en hoe het item er toen uitzag, zodat zichtbaar is of de correctie geland is:

```bash
python "<skill>/scripts/review_server.py" \
  --input "<werkmap>/activiteit-2/ronde-2/analyse.json" \
  --activiteit 2 \
  --feedback-out "<werkmap>/activiteit-2/ronde-2/feedback.json" \
  --ronde 2 \
  --vorige "<werkmap>/activiteit-2/ronde-1"
```

Default poort 3118. Start de server in de achtergrond, geef de analist de URL
(`http://localhost:3118`), en **pauzeer**: rond je beurt af met een duidelijke instructie
("Bekijk de review, geef desgewenst feedback en klik op de verstuurknop (leeg = akkoord), en
laat het me weten als je klaar bent").
Ga niet zelf door tot de analist bevestigt.

## Schema — `feedback.json` (door de viewer geschreven, per ronde)

```json
{
  "status": "akkoord",            // of "wijzigingen"
  "activiteit": "2",
  "items": { "m2": "Plichthebbende benoemen.", "v1": "Volg deze delegatie wél verder." },
  "algemeen": "Markering voor 'partner' ontbreekt in bron br2."
}
```

Een `akkoord` **zonder** `items`/`algemeen` rondt de analyse act2-only af (`scope: "act2"`).
In het reviewlog van het rapport draagt elke ronde ook haar `status` mee.

In activiteit 2 kan een `items`-sleutel ook een **verwijzing-id** (`v1`, …) zijn: zo stuurt
de analist het scope-besluit bij ("volg deze delegatie wél verder", "deze hoort buiten
scope", "promoveer deze tot eigen bron"). Verwerk dat als een aanpassing van `status`/`functie`
van de betreffende verwijzing (of als een nieuwe bron) in de volgende ronde.

Gebruik **stabiele id's** en **houd ze stabiel tussen rondes**: hetzelfde concept houdt
hetzelfde id, ook na een correctie. Daarop koppelt de feedback terug én daarop matcht de
viewer de vorige versie van een item.

## De iteratieve lus

De review herhaalt zich tot de analist akkoord is zonder verdere opmerkingen:

1. **Schrijf** `ronde-{N}/analyse.json` en start de server (ronde 1 zonder `--vorige`,
   ronde 2+ met `--vorige ronde-{N-1}` en `--ronde N`).
2. **Pauzeer** en wacht tot de analist bevestigt dat die klaar is.
3. **Lees** `ronde-{N}/feedback.json`.
   - Bij `status: "akkoord"` **zonder** `items` en **zonder** `algemeen`: de lus is klaar.
     Stop de server en ga door naar het rapport.
   - Anders: verwerk **elk** gevuld veld. Per `id` pas je de betreffende markering /
     verwijzing aan (herclassificeren, toelichting bijstellen,
     bron toevoegen/verwijderen). De `algemeen`-tekst kan leiden tot toegevoegde of
     verwijderde items, of methodische aanpassingen. Stop de server, verhoog `N`, en ga
     terug naar stap 1 met het herziene resultaat.
4. **Veiligheidscap:** stop na maximaal **6 rondes**, ook als er nog feedback is. Meld dit
   aan de analist en noteer het in de reviewlog (de resterende punten horen dan bij de
   aandachtspunten voor validatie).

Houd per ronde bij wat je hebt gewijzigd; het aantal rondes en de wijzigingen komen in de
**Reviewlog** van het eindrapport.

## Niet-interactief draaien (alleen voor evals/automatisering)

Bij `WETSANALYSE_NO_REVIEW=1` in de omgeving sla je de hele lus over: schrijf één keer
`ronde-1/analyse.json` (geen server, geen pauze) en noteer in het eindrapport dat de
reviews zijn overgeslagen. Gebruik dit uitsluitend voor geautomatiseerde tests; voor
mensen blijven de checkpoints altijd aan.
