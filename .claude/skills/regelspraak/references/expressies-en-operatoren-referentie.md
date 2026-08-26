# Expressies, operatoren en predicaten — referentie

De exacte taalpatronen voor expressies in resultaat-, voorwaarden- en variabelendeel
(RegelSpraak-specificatie v2.3.0, hfst 5–8). **Dit is de plek waar verzinnen het meest loert:
gebruik uitsluitend de woorden hieronder.** Schrijf bijvoorbeeld nooit "som van" voor optellen of
"vermeerderd met" — die bestaan niet als operator. Voorbeelden komen uit de TOKA-casus.

## Inhoud
1. [Onderwerpexpressies en selectie](#1-onderwerpexpressies-en-selectie)
2. [Subselectie en concatenatie](#2-subselectie-en-concatenatie)
3. [Aggregatie-expressies](#3-aggregatie-expressies)
4. [Rekenkundige operatoren](#4-rekenkundige-operatoren)
5. [Afronding en begrenzing](#5-afronding-en-begrenzing)
6. [Literals, rekendatum en rekenjaar](#6-literals-rekendatum-en-rekenjaar)
7. [Predicaten (condities)](#7-predicaten-condities)
8. [Tijdsafhankelijkheid](#8-tijdsafhankelijkheid)

---

## 1. Onderwerpexpressies en selectie

Een **onderwerpexpressie** bepaalt op welke instanties een regel wordt toegepast.

- **Onderwerp** = naam van het objecttype: `een Natuurlijk persoon`, of via een rol/kenmerk:
  `een passagier`, `een belaste reis`.
- **Universeel onderwerp** (lidwoord `een`): elke regel moet er minstens één bevatten — het geeft
  aan op welke instanties de regel draait.
- **Selectie** met `van`: verwijst naar een attribuut/rol van het onderwerp:
  `de leeftijd van een Natuurlijk persoon`.
- **Onderwerpverwijzing** (`de`/`het`): verwijst naar dezelfde instantie als het universele
  onderwerp. Bij meerdere onderwerpen met dezelfde naam: een **rangtelwoord** toevoegen.
- **Bezield**: `hij` (verwijzend) en `zijn` (bezittelijk): `zijn geboortedatum`.
- **Onderwerpketen** via rollen: `een passagier van een Vlucht`, `de reis van een Natuurlijk
  persoon`. Met een meervoudige rol + kwantificatie: `de leeftijden van alle passagiers van de
  Vlucht`.

## 2. Subselectie en concatenatie

**Subselectie** maakt een groep instanties/waarden die aan een predicaat voldoen, met `die`/`dat`:
```
Het aantal minderjarige passagiers van een reis moet berekend worden als het aantal passagiers
van de reis die die minderjarig zijn.
```
Meerdere selectiecriteria: `aan alle/geen/precies/ten minste/ten hoogste <n> van de volgende
voorwaarden voldoet` na `die`.

**Concatenatie** voegt verzamelingen samen met `en` (tussen de laatste twee; eerdere gescheiden
door komma's):
```
Het aantal uitzonderingspassagiers van een reis moet berekend worden als het aantal passagiers
van de reis die die minderjarige zijn, passagiers van de reis die een passagier van 18 tot en
met 24 jaar zijn en passagiers van de reis die een passagier van 65 jaar of ouder zijn.
```
**Uitzondering:** in een conditie met het predicaat `is gelijk aan` wordt `of` gebruikt i.p.v.
`en`:
```
de luchthaven van vertrek van de Vlucht is gelijk aan 'Amsterdam Schiphol' of 'Groningen Eelde'
```

## 3. Aggregatie-expressies

Aggregatie zet een meervoudige invoer om naar één waarde. De exacte functies:

| Functie | Taalpatroon |
| --- | --- |
| Telling van instanties | `het aantal <meervoudige expressie>` |
| Sommatie | `de som van <meervoudige numerieke expressie>` |
| Maximum | `de maximale waarde van <meervoudige expressie>` |
| Minimum | `de minimale waarde van <meervoudige expressie>` |
| Eerste datum (oudste) | `de eerste van <datumexpressie>, …` |
| Laatste datum (jongste) | `de laatste van <datumexpressie>, …` |

```
De totaal te betalen belasting van een reis moet berekend worden als de som van de te betalen
belasting van alle passagiers van de reis.

De leeftijd van de oudste passagier van een reis moet gesteld worden op de maximale waarde van
de leeftijden van alle passagiers van de reis.
```
**Lege waardes:** bij `de som van` tellen lege waardes niet mee (en als álle leeg zijn, is het
resultaat leeg). Forceer 0 met de toevoeging `of 0 als die er niet zijn`:
```
… moet berekend worden als de som van de te betalen belasting van alle passagiers van de reis
of 0 als die er niet zijn.
```
Aggregatie **over dimensies** met `vanaf <label> t/m <label>`:
```
De betaalde belasting over de afgelopen vier jaar van een Natuurlijk persoon moet berekend
worden als de som van zijn betaalde belasting in jaar vanaf vier jaar geleden t/m een jaar geleden.
```

## 4. Rekenkundige operatoren

De **enige** rekenkundige operatoren (de eerste expressie staat vóór de operator, de tweede erna):

| Bewerking | Operator(en) |
| --- | --- |
| Optellen | `plus` |
| Aftrekken | `min` of `verminderd met` |
| Vermenigvuldigen | `maal` |
| Delen | `gedeeld door` of `gedeeld door (ABS)` |
| Worteltrekken | `de wortel van <expressie>` |
| Machtsverheffen | `<expressie> tot de macht <expressie>` |
| Percentage van | `<percentage> van <expressie>` |
| Absolute waarde | `de absolute waarde van <expressie>` |

```
de leeftijd van een passagier plus 1 jr
zijn belasting op basis van afstand plus zijn belasting op basis van reisduur
het HOGE BTW PERCENTAGE maal de prijs van de Eenheid energie
```
**Rekenvolgorde:** eerst `de wortel van`, dan `maal`/`gedeeld door`, dan `plus`/`min`/`verminderd
met`; bij gelijke prioriteit eerst de linker operatie. Gebruik haakjes `(` `)` om de volgorde te
sturen. **Eenheden** moeten via een eenheidssysteem op elkaar afgestemd zijn. Bij `plus`/`min`
wordt een lege waarde als 0 behandeld (bij `de som van` níet — zie §3).

Datum-rekenen: `de tijdsduur van <datum> tot <datum> in <eenheid>` (bv. `in hele jaren`),
`<datum> plus/min <tijdseenheid>`, `het jaar/de maand/de dag … uit <datum>`, `de eerste paasdag
van <jaar>` — zie spec §6.10–6.13.

## 5. Afronding en begrenzing

**Afronden:** `<expressie> <methode> afgerond op <n> decimalen`. De vijf methodes:
`naar beneden` · `naar boven` · `rekenkundig` · `richting nul` · `weg van nul`.
```
De te betalen belasting van een passagier moet gesteld worden op zijn belasting op basis van
afstand naar beneden afgerond op 0 decimalen.
```
**Begrenzen:** `<expressie>, met een minimum van <expr>` en/of `met een maximum van <expr>`.
```
De te betalen belasting van een passagier moet berekend worden als zijn belasting op basis van
afstand min korting bij gebruik niet-fossiele brandstof, met een minimum van 0 € en een maximum
van 1000 € naar beneden afgerond op 0 decimalen.
```

## 6. Literals, rekendatum en rekenjaar

- **Literal expressie** — een enkele waarde, evt. met eenheid: `9`, `49 jr`, `08-12-2022`,
  `waar`/`onwaar`, `'Amsterdam Schiphol'` (enumeratiewaarde, enkele quotes), `"Jan Jansen"`
  (tekst, dubbele quotes).
- **Rekendatum / Rekenjaar** — de datum/het jaar dat bij uitvoering wordt opgegeven; bepaalt welke
  regelversie geldt en kan ook als expressie in een regel gebruikt worden:
  ```
  De leeftijd van een Natuurlijk persoon moet berekend worden als de tijdsduur van zijn
  geboortedatum tot de Rekendatum in hele jaren.
  ```

## 7. Predicaten (condities)

Een predicaat staat doorgaans achter een onderwerpexpressie en levert waar/onwaar. Hieronder de
**stellende vorm** (gebruikt in een lijst met bullets); in een enkele conditie wordt de
**vragende** vorm met `indien` ervoor gebruikt. Voor het volledige overzicht: spec Tabel 16.

### Vergelijkingen
| Stellende vorm | Datatype |
| --- | --- |
| `is gelijk aan` / `is ongelijk aan` | alle |
| `is groter dan` / `is groter of gelijk aan` | Numeriek/Percentage |
| `is kleiner dan` / `is kleiner of gelijk aan` | Numeriek/Percentage |
| `is later dan` / `is later of gelijk aan` | Datum-tijd |
| `is eerder dan` / `is eerder of gelijk aan` | Datum-tijd |
```
de afstand tot bestemming van de Vlucht is kleiner dan de bovengrens afstand eerste schijf
de uiterste boekingsdatum van de Vlucht is eerder dan de datum van vertrek van de Vlucht
```

### Lege waardes
`is leeg` / `is gevuld` (vragend: `leeg is` / `gevuld is`):
```
zijn leeftijd is gevuld
```

### Overige predicaten
- **Elfproef:** `voldoet aan de elfproef` (BSN-controle).
  ```
  zijn burgerservicenummer voldoet aan de elfproef
  ```
- **Getalcontrole** (op Tekst): `is numeriek met exact <n> cijfers`.
  ```
  zijn burgerservicenummer is numeriek met exact 9 cijfers
  ```
- **Dagsoortcontrole** (op Datum-tijd): `is een <dagsoort>` / `is geen <dagsoort>`.
  ```
  de datum van vertrek van een Vlucht is een kerstdag
  ```
- **Uniciteit** (alleen in consistentieregels): `de <attribuut> van alle <objecttype> moeten uniek
  zijn`, eventueel `verenigd met …` of via `de concatenatie van …`.
- **Rolcheck:** `is een <rol>` / `is geen <rol>`, of `<onderwerp> heeft een <rol>`.
  ```
  hij is een passagier
  de Vlucht heeft een passagier
  ```
- **Kenmerkcheck:** bijvoeglijk `is <kenmerk>`/`is niet <kenmerk>`; bezittelijk `heeft
  <kenmerk>`/`heeft geen <kenmerk>`; overig `is een <kenmerk>`/`is geen <kenmerk>`.
  ```
  hij is minderjarig
  ```

### Samengestelde condities
Lijst met bullets `•` + kwantificatie. Enkel-instantie:
`indien hij aan <kwantificatie> volgende voorwaarden voldoet:`. Kwantificaties:
`alle` · `geen van de` · `ten minste <n>` · `ten hoogste <n>` · `precies <n>` `van de` (met `<n>`
als woord: één/twee/drie/vier, of een getal). Check op volledige periode:
`(is) gedurende het gehele jaar/de gehele maand …`.

## 8. Tijdsafhankelijkheid

Een expressie die tijdsafhankelijke attributen/parameters/kenmerken gebruikt, levert een
tijdsafhankelijk resultaat (behalve de aggregatie `het totaal van`, spec §7.1). De tijdlijn van het
afgeleide attribuut moet aansluiten op de tijdlijnen van de invoer. Een tijdsafhankelijke conditie
gaat vooraf door `gedurende de tijd dat …`; bij gebruik bij een expressie zet je die expressie
tussen haakjes of legt je haar als variabele vast. Een specifieke periode: `van dd. <datum> tot
dd. <datum>` / `het is de periode van dd. <datum> tot dd. <datum>`. Zie spec hfst 5.1 + 7 + 8.4
voor de details.
