# Vertaalpatronen — van wetsanalyse naar GegevensSpraak + RegelSpraak

De brug tussen het duiden (skill `wetsanalyse`: JAS-klassen, begrippen, afleidingsregels) en het
formaliseren (deze skill: GegevensSpraak + RegelSpraak). Lees dit voordat je vertaalt. Het beschrijft
(1) hoe je een wetsanalyse-`rapport.json` inleest, (2) de afbeelding van JAS-klassen op
GegevensSpraak/RegelSpraak, (3) hoe afleidingsregels resultaatacties worden, (4) het
standalone-pad vanaf wettekst, en (5) de grenzen en valkuilen bij het formaliseren.

## 1. Een wetsanalyse-rapport.json inlezen

Een afgeronde wetsanalyse levert per **werkgebied** één `rapport.json` op (zie de wetsanalyse-skill).
Lees dat niet handmatig over maar draai `scripts/ingest_rapport.py` (zie SKILL.md stap 1): dat schrijft
een `ingest.json` met exact de onderstaande delen en behoudt de herkomst-id's. De relevante delen voor
formalisering (zoals ze in `ingest.json` staan):

- **`bronnen`** — de tekstdelen (`bron_id`, `label`, `bwbId`, `artikel`, `lid`, `bronreferentie`),
  incl. de `Brondefinitie`-markeringen (`brondefinities`) en de act-2-markeringen waar een
  begrip/regel via `markering_ids` op steunt (`gekoppelde_markeringen` — herkomst-context).
  Gebruik deze voor de **`herkomst`** van je declaraties en regels (`vindplaatsen: [{bron_id, lid}]`).
- **`begrippen`** (activiteit 3a) — per begrip: `naam` (voorkeursterm), `synoniemen`, `klasse`
  (JAS-klasse), `definitie` (+ `is_interpretatie`: true = werkdefinitie van de analist),
  `grondformulering`, `voorbeeld`, `kenmerken`, `relaties` (gestructureerd: soort/beschrijving/
  `doel_begrip`), `vindplaatsen`, `markering_ids` (de act-2-markeringen waarop het begrip berust),
  `verwijst_naar_begrippen` (begrip-id's gebruikt in de omschrijving) en `bron_verwijzing` (id van de
  definitie-verwijzing). Dit voedt **GegevensSpraak**. `bron_verwijzing` is het signaal voor een
  **domein/begripsomschrijving** en voor de herleidbaarheid (een hergebruikte wettelijke definitie);
  het komt mee in `ingest.json`. Een `relatie` tussen twee begrippen is de kandidaat voor een
  **feittype + rollen**.
- **`afleidingsregels`** (activiteit 3b) — per regel: `naam`, `type`, en de **begrip-id-gebouwde**
  velden `uitvoer` (`{begrip_id, toelichting}` — verplicht gevuld), `invoer`
  (`[{begrip_id, toelichting}]`), `parameters` (`[{begrip_id, waarde, eenheid, geldigheid,
  vindplaats, toelichting}]`) en `voorwaarden` (`[{tekst, begrip_ids, verbinding}]`), plus
  `markering_ids` en `vindplaatsen`. Het `type` is één van de (lowercase) enum-waarden
  `rekenregel` / `beslisregel` / `specialisatieregel` (zo gevalideerd in de wetsanalyse). Dit voedt
  **RegelSpraak**. De regel is hier *geannoteerd*, niet uitgeschreven — jij formuleert hem hier voor
  het eerst uit in RegelSpraak.

Werkwijze: doorloop eerst **alle begrippen** → bouw GegevensSpraak (stap 2). Doorloop daarna **alle
afleidingsregels** → schrijf RegelSpraak-regels (stap 3). De `naam` van een begrip is leidend voor de
`naam` van het bijbehorende objecttype/attribuut/kenmerk/parameter — **verzin geen nieuwe termen**.

**Koppeling op id, niet op naam.** Elke GegevensSpraak-declaratie draagt in `herkomst.begrip_ids`
het bron-begrip-id (`b*`). De regelvelden verwijzen met datzelfde `begrip_id` — zo weet je bij het
uitschrijven van een regel **exact** welk attribuut/kenmerk/parameter bedoeld is: volg
`uitvoer.begrip_id` → het begrip → de declaratie met dat id in haar `herkomst`. Match nooit op
naam-strings (synoniemen en spellingsvarianten breken dat).

## 2. JAS-klasse → GegevensSpraak/RegelSpraak

| JAS-klasse (wetsanalyse) | Wordt in RegelSpraak | Hoe |
| --- | --- | --- |
| **Rechtssubject** | Objecttype (vaak `(bezield)`) | Drager van rechten/plichten → een objecttype; persoon/organisatie → bezield/onbezield. |
| **Rechtsobject** | Objecttype of attribuut | Zelfstandig "ding" → objecttype; eigenschap van een subject → attribuut. |
| **Rechtsbetrekking** | Feittype + rollen | Relatie tussen twee subjecten (recht/plicht) → een feittype met twee rollen (rechthebbende/plichthebbende). |
| **Rechtsfeit** | Regel-trigger / ObjectCreatie / FeitCreatie | Handeling/gebeurtenis die een betrekking creëert → meestal een voorwaarde of een creatie-actie. |
| **Voorwaarde** | Voorwaardendeel (`indien …`) | Conditie voor een rechtsgevolg → de conditie in het voorwaardendeel van de regel. |
| **Afleidingsregel** | RegelSpraak-`Regel` (resultaatdeel) | Zie §3 hieronder. |
| **Variabele en variabelewaarde** | Attribuut (+ datatype) | Kenmerk dat per geval verschilt → attribuut; de mogelijke waarden bepalen het datatype/domein/enumeratie. |
| **Parameter en parameterwaarde** | Parameter | Vaste waarde gelijk voor allen → `Parameter …` (geen hard getal in de regel). |
| **Operator** | Rekenkundige operator / predicaat | Bewerking/vergelijking/logica → de operator/predicaat uit `expressies-en-operatoren-referentie.md`. |
| **Tijdsaanduiding** | Datum-tijd-attribuut / tijdlijn / dagsoort | Peildatum/tijdvak → Datum-tijd-datatype, een tijdlijn op het attribuut, of een dagsoort. |
| **Plaatsaanduiding** | Attribuut (Tekst/enumeratie) of domein | Plaats/gebied dat bereik bepaalt → attribuut met enumeratiedomein (bv. luchthavens/lidstaten). |
| **Delegatiebevoegdheid en delegatie-invulling** | (meestal) validatiepunt | De gedelegeerde regeling is een eigen bron; formaliseer pas als de invulling is opgehaald — anders signaleren. |
| **Brondefinitie** | Domein / begripsomschrijving | Wettelijke definitie → een domein (bij een waardesoort) of de leidende betekenis van een objecttype/attribuut; hergebruik de definitie letterlijk. |

**Vuistregels.**
- Booleaanse/ja-nee-eigenschappen → liever een **kenmerk** dan een Boolean-attribuut (GegevensSpraak
  §5). "is X" → bijvoeglijk; "heeft recht op X" → bezittelijk; anders overig.
- Een vaste waarde (tarief, drempel, percentage) → **parameter**, niet hardcoden in de regel.
- Een limitatieve opsomming → **enumeratiedomein**.
- Een geldbedrag/percentage dat vaak terugkomt → een **domein** (bv. `Bedrag`).
- Twijfel je tussen objecttype en attribuut, of mist de wet een definitie? Kies de best passende,
  leg het vast in `twijfel`, en neem het op bij de validatiepunten.

## 3. Afleidingsregel → resultaatactie

Het `type` van de wetsanalyse-afleidingsregel (lowercase enum: `rekenregel` / `beslisregel` /
`specialisatieregel`) bepaalt de RegelSpraak-resultaatactie:

| Afleidingsregel-`type` | Resultaatactie | Taalpatroon (zie regels-referentie) |
| --- | --- | --- |
| **`rekenregel`** (berekent bedrag/getal) | **Gelijkstelling — berekening** | `De <attribuut> van een <onderwerp> moet berekend worden als <expressie>` |
| **`beslisregel`** (ja/nee, waar/onwaar) | **Kenmerktoekenning** of **Consistentieregel** | `Een <objecttype> is/heeft <kenmerk> indien …` (toekenning) of `… moet voldoen aan …` (controle) |
| **`specialisatieregel`** (behoort tot doelgroep) | **Kenmerktoekenning** | `Een <objecttype> is een <kenmerk> indien …` |

Vertaal vervolgens de onderdelen van de afleidingsregel (alle referenties zijn **begrip-id's** —
volg ze naar de declaratie met dat id in `herkomst.begrip_ids`, match niet op naam):
- `uitvoer.begrip_id` → het attribuut/kenmerk in het resultaatdeel.
- `invoer[].begrip_id` + `parameters[].begrip_id` → de attributen/parameters in de expressie.
- `parameters[]` draagt de gestructureerde parameterwaarde: `waarde` + `eenheid` →
  de **GegevensSpraak-parameterdeclaratie** (bv. `Parameter het tarief : Percentage`) mét de
  waarde; `geldigheid` → een **regelversie** (`geldig vanaf …`) wanneer de waarde tijdgebonden is;
  een lege `waarde` betekent: de waarde staat in een (nog niet geanalyseerde) delegatie →
  declareer de parameter zonder waarde en noteer een validatiepunt.
- `voorwaarden[]` → het **voorwaardendeel**: één conditie → enkelvoudig `indien …`; meerdere
  condities → een **samengestelde voorwaarde** met bullets, waarbij `verbinding` de kwantor
  bepaalt (alle EN → `aan alle volgende voorwaarden`, alle OF → `aan ten minste één van de
  volgende voorwaarden`; gemengd → nesten of splitsen). De `tekst` blijft dicht op de wettekst;
  de `begrip_ids` wijzen de operanden aan.
- De **expressie** in het resultaatdeel leid je af uit `uitvoer` (= het te berekenen
  attribuut/kenmerk), `invoer` + `parameters` (= de operanden) en de letterlijke wettekst op
  de `vindplaatsen`/`markering_ids`. Gebruik uitsluitend de **echte** RegelSpraak-operatoren
  (`plus`, `min`, `maal`, `de som van`, …) uit `expressies-en-operatoren-referentie.md`; verzin
  niets. Is de rekenwijze in de wet niet eenduidig, leg de keuze vast in `twijfel` en bij de
  validatiepunten.

Een directe toekenning zonder berekening → `… moet gesteld worden op <waarde>`. Een attribuut dat niet
leeg mag zijn → overweeg **Initialisatie**. Een verdeling van een totaal over instanties → **Verdeling**
(markeer de verdeelsleutel als validatiepunt bij twijfel).

## 4. Standalone-pad — vanaf wettekst (zonder rapport.json)

Is er geen wetsanalyse-rapport, dan werkt de skill zelfstandig. **Advies eerst:** stel de gebruiker
voor om de `wetsanalyse`-skill te draaien — een goede JAS-duiding maakt de formalisering betrouwbaarder
en levert de begrippen/afleidingsregels kant-en-klaar. Wil de gebruiker direct door, doe dan een
**lichte** identificatie:

1. Haal de actuele wettekst op via de wettenbank-MCP: `wettenbank_zoek` (BWB-id) →
   `wettenbank_structuur` (juiste artikel + definitieartikelen) → `wettenbank_artikel` (letterlijke
   tekst, leden, `bronreferentie`). Gebruik `wettenbank_zoekterm` voor brondefinities.
2. Identificeer per lid de **gegevens** (wie/wat = objecttypen; eigenschappen = attributen/kenmerken;
   vaste waarden = parameters; relaties = feittypen) en de **regels** (wat wordt bepaald/berekend/
   gecontroleerd, onder welke voorwaarden). Houd dit licht — je hoeft geen volledige JAS-markering te
   doen, maar gebruik de klassen uit §2 als denkraam.
3. Leg de **`herkomst`** vast op de letterlijke wettekst (`bron_id` afgeleid van artikel+lid, plus de
   `bronreferentie`/jci-link). Brongetrouwheid blijft gelden: citeer letterlijk, verzin geen tekst.
4. Vervolg met stap 2 (GegevensSpraak) en stap 3 (RegelSpraak) zoals in `SKILL.md`.

Is de MCP niet beschikbaar, zeg dat eerlijk en werk met door de gebruiker aangeleverde tekst, met
dezelfde brongetrouwheid.

## 5. Grenzen en valkuilen bij formaliseren

De syntax hieronder bestáát al in `expressies-en-operatoren-referentie.md`; de fout zit doorgaans
niet in onbekende taal maar in de *keuze* van het modelpatroon. Vier terugkerende valkuilen:

- **Een booleaan zegt *dát*, niet *wanneer*.** Bepaalt de wet een moment of termijn (bv.
  "invorderbaar ná X dagen", "uiterlijk Y weken na dagtekening"), dan is een kenmerk (`is
  invorderbaar`) niet genoeg — het legt alleen vast *dát* iets geldt, niet *per wanneer*. Modelleer
  een **datum-/duur-attribuut** en bereken het met `de tijdsduur van <datum> tot <datum> in
  <eenheid>` of `<datum> plus/min <tijdseenheid>` (expressies §4/§6), met de termijn als
  **parameter** in de expressie. **Vuistregel/diagnose:** een gedeclareerde parameter die door geen
  enkele regel wordt gebruikt (de validator waarschuwt hierop) is bijna altijd het signaal dat
  juist deze rekenregel ontbreekt — voeg de regel toe of haal de parameter weg.
- **Rolcheck vs lege-waarde.** Wil je toetsen of een gerelateerd object *bestaat* (bv. "de
  bijbehorende belastingaanslag"), gebruik dan de **rolcheck** `<onderwerp> heeft een <rol>` of `is
  (g)een <rol>` (expressies §7). `is gevuld`/`is leeg` is uitsluitend voor de leegte van een
  **attribuut**, niet voor het bestaan van een rol-relatie.
- **Limitatieve opsomming → één enumeratiedomein, niet parallelle kenmerken.** Sluiten de
  categorieën elkaar uit (navorderingsaanslag / naheffingsaanslag / uitnodiging tot betaling / …),
  modelleer dan **één** `type`-attribuut met een **enumeratiedomein** en **declareer dat domein ook
  echt**. Vermijd de dubbele representatie — een `type`-attribuut én een rij losse kenmerken voor
  dezelfde categorie — want die kan inconsistent raken en legt de wederzijdse uitsluiting niet vast.
- **Iteratie kent RegelSpraak v2.3.0 niet vrij.** Een onbekend of onbegrensd aantal stappen (bv.
  "elke volgende invorderingstermijn") laat zich niet als een vrije lus uitdrukken. Is het aantal
  telbaar en begrensd → overweeg een **dimensie** (`vanaf <label> t/m <label>`, expressies §3);
  anders **noteer het expliciet als validatiepunt** en formaliseer het niet. Verzin geen
  iteratieconstructie.
