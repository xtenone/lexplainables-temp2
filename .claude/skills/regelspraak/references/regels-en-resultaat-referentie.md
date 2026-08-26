# RegelSpraak-regels — structuur, resultaatdeel, voorwaardendeel, variabelendeel

De structuur van een RegelSpraak-regel en de exacte taalpatronen van de acht resultaatacties
(RegelSpraak-specificatie v2.3.0, hfst 4 + 9 + 10 + 11). Gebruik **alleen** deze patronen.
Voorbeelden komen uit de TOKA-casus. Voor expressies/operatoren/predicaten in deze patronen: zie
`expressies-en-operatoren-referentie.md`.

## Inhoud
1. [Regelstructuur (regel, regelversie, basispatroon)](#1-regelstructuur)
2. [Resultaatdeel — de acht acties](#2-resultaatdeel--de-acht-acties)
3. [Voorwaardendeel](#3-voorwaardendeel)
4. [Variabelendeel](#4-variabelendeel)

---

## 1. Regelstructuur

Een RegelSpraak-regel bestaat uit:
1. een **regel** met een naam (`Regel <naam>`),
2. één of meer **regelversies** met een geldigheidsperiode,
3. per versie een **basispatroon**: resultaatdeel (verplicht) + voorwaardendeel (optioneel) +
   variabelendeel (optioneel).

```
Regel bepaal leeftijd
  geldig altijd
    De leeftijd van een Natuurlijk persoon moet berekend worden als de tijdsduur van zijn
    geboortedatum tot de datum van de vlucht van zijn reis in hele jaren.
```

### Regelversie en geldigheid
Elke versie begint met `geldig`, gevolgd door de periode:
- `geldig altijd` (tweezijdig open),
- `geldig vanaf <datum> t/m <datum>` (gesloten interval; jaartal mag: `vanaf 2020 t/m 2021`),
- `geldig vanaf <datum>` of `geldig t/m <datum>` (eenzijdig open).

Geldigheidsperioden van verschillende versies van dezelfde regel mogen **niet overlappen**. Bij
uitvoering bepaalt de **rekendatum** welke versie geldt. Voorbeeld met twee versies:
```
Regel bepaal af te dragen omzetbelasting op energie
  geldig t/m 30-06-2022
    De af te dragen omzetbelasting van een Eenheid energie moet berekend worden als het
    HOGE BTW PERCENTAGE maal de prijs van de Eenheid energie.
  geldig vanaf 01-07-2022 t/m 31-12-2022
    De af te dragen omzetbelasting van een Eenheid energie moet berekend worden als het
    LAGE BTW PERCENTAGE maal de prijs van de Eenheid energie.
```

### Basispatroon
```
<regelSpraakregel> ::= <resultaatdeel> \n [<voorwaardendeel>] "." [<variabelendeel>]
```
Het voorwaardendeel wordt afgesloten met een **punt** (`.`). Elke RegelSpraak-regel bevat ten
minste één **onderwerpexpressie**, waarvan minstens één een *universeel onderwerp* is (zie de
expressies-referentie). Een **bezield** objecttype kun je in vervolgverwijzingen aanduiden met
`hij`/`zijn`.

## 2. Resultaatdeel — de acht acties

Het resultaatdeel beschrijft de actie en is verplicht. Kies de passende actie:

### 2.1 Gelijkstelling
Een attribuut krijgt een waarde. Twee taalpatronen:
- **Berekening** (uit een expressie):
  `De/het <attribuut> van een <onderwerp> moet berekend worden als <expressie>`
  ```
  De te betalen belasting van een Natuurlijk persoon moet berekend worden als
  zijn belasting op basis van afstand plus zijn belasting op basis van reisduur.
  ```
- **Directe toekenning** (een waarde):
  `De/het <attribuut> van een <onderwerp> moet gesteld worden op <waarde>`
  ```
  De te betalen belasting van een Natuurlijk persoon moet gesteld worden op zijn
  belasting op basis van afstand.
  ```
Linker- en rechterkant moeten **hetzelfde datatype** hebben; verschillende eenheden moeten via een
eenheidssysteem in elkaar omrekenbaar zijn.

### 2.2 Kenmerktoekenning
Bepaalt dat een instantie een kenmerk krijgt. Taalpatroon hangt af van de kenmerksoort (zie
GegevensSpraak §5):
- overig: `Een <objecttype> is een <kenmerk>` → `Een Vlucht is een belaste reis`
- bijvoeglijk: `Een <objecttype> is <kenmerk>` → `Een Vlucht is duurzaam`
- bezittelijk: `Een <objecttype> heeft <kenmerk>` → `Een passagier heeft recht op korting`

Normaal volgt een voorwaardendeel dat beschrijft wanneer het kenmerk van toepassing is:
```
Regel Kenmerktoekenning persoon minderjarig
  geldig altijd
    Een Natuurlijk persoon is minderjarig
    indien zijn leeftijd kleiner is dan de volwassenleeftijd.
```
**Belangrijk:** kenmerken zijn onwaar als er geen kenmerktoekenning is. Een *negatieve*
kenmerktoekenning (`is niet …`) bestaat niet en is niet toegestaan.

### 2.3 ObjectCreatie
Maakt tijdens uitvoering een nieuwe instantie van een objecttype, in relatie met een bestaande
instantie (via een feittype). Taalpatroon: `Een <onderwerp> heeft een <rol>`, eventueel met
attribuut-/kenmerkwaarden via `met … gelijk aan …`:
```
Regel vastgestelde contingent treinmiles
  geldig altijd
    Een Vlucht heeft het vastgestelde contingent treinmiles met
    aantal treinmiles op basis van aantal passagiers gelijk aan het aantal passagiers
    van de Vlucht maal het aantal treinmiles per passagier voor contingent.
```

### 2.4 FeitCreatie
Maakt een nieuw feit (relatie) tussen bestaande instanties. Taalpatroon:
`Een <rol> van een <onderwerp> is een <rol> van de <onderwerp>`:
```
Regel passagier met recht op treinmiles
  geldig altijd
    Een passagier met recht op treinmiles van een vastgestelde contingent treinmiles is
    een passagier van de reis met treinmiles van het vastgestelde contingent treinmiles.
```

### 2.5 Consistentieregel
Controleert of de waarde van een attribuut, rol of instantie aan criteria voldoet; levert
`inconsistent` als dat niet zo is. Geschreven als verplichting met `moet(en)`.
- Enkel criterium:
  ```
  Regel Controleer of vlucht geen rondvlucht is
    geldig altijd
      De luchthaven van vertrek van een Vlucht moet ongelijk zijn aan de luchthaven van
      bestemming van de Vlucht.
  ```
- Meerdere criteria (`moet voldoen aan <kwantificatie> volgende criteria:` + bullets):
  ```
  Regel Controleer of de TOKA wet van toepassing is
    geldig altijd
      Een reis moet voldoen aan ten minste één van de volgende criteria:
      • de reis is belast
      • het aantal passagiers van de reis is groter dan 0.
  ```

### 2.6 Initialisatie
Voor attributen waarvan de waarde niet leeg mag zijn: kent een waarde toe als het attribuut leeg
is. `De/het <attribuut> van een <onderwerp> moet geïnitialiseerd worden op <waarde>`:
```
Regel Initialiseer te betalen belasting op initiele belasting
  geldig altijd
    De te betalen belasting van een passagier moet geïnitialiseerd worden op de initiele belasting.
```

### 2.7 Verdeling
Verdeelt de waarde van een numeriek attribuut over een attribuut van meerdere instanties van een
ander objecttype (bv. treinmiles over passagiers). Zie spec §9.7 voor de varianten (over alle
ontvangers, over groepen in een volgorde, met maximale aanspraak, met afronding, onverdeelde rest).
Markeer een verdeling als validatiepunt als de verdeelsleutel uit de wet niet eenduidig is.

### 2.8 Dagsoortdefinitie en Startpuntbepaling
- **Dagsoortdefinitie** legt vast wanneer een datum van een bepaalde dagsoort is (zie
  GegevensSpraak §11); bevat voorwaarden die de dag bepalen.
- **Startpuntbepaling** bepaalt het variabele startpunt van een tijdlijn (zie GegevensSpraak §8):
  ```
  Het startpunt van een periode van een kwartaal vanaf de geboortedatum voor een passagier
  wordt bepaald door zijn geboortedatum.
  ```

## 3. Voorwaardendeel

Optioneel; beschrijft de voorwaarden waaronder het resultaatdeel wordt uitgevoerd. Drie vormen:
1. `indien <conditie>` — meest gebruikt.
2. `gedurende de tijd dat <tijdsafhankelijke conditie>`.
3. Direct een tijdsafhankelijke voorwaarde als periode (`vanaf … tot …`, `tot en met …`).

Het voorwaardendeel eindigt met een **punt**. Een conditie is **enkel** (één predicaat) of
**samengesteld** (een lijst met bullets `•` + een **kwantificatie**):
`alle` / `geen van de` / `ten minste <n>` / `ten hoogste <n>` / `precies <n>` `van de`.

```
Regel recht op duurzaamheidskorting
  geldig altijd
    Een passagier heeft recht op duurzaamheidskorting
    indien hij aan alle volgende voorwaarden voldoet:
    • zijn reis is duurzaam
    • de afstand tot bestemming van zijn reis is groter of gelijk aan duurzaamheidskorting minimale afstand.
```
Geneste samengestelde condities krijgen per niveau een extra bullet (`••`, `•••`, …). Voor de
predicaten en kwantificaties: zie `expressies-en-operatoren-referentie.md`.

## 4. Variabelendeel

Optioneel; begint met `Daarbij geldt:` en definieert lokale variabelen die in het resultaat- én
voorwaardendeel bruikbaar zijn. Houdt regels overzichtelijker.
```
Regel Kenmerktoekenning persoon minderjarig
  geldig altijd
    Een Natuurlijk persoon is minderjarig
    indien X kleiner is dan de volwassenleeftijd.
    Daarbij geldt:
      X is de tijdsduur van zijn geboortedatum tot de datum van de vlucht in hele jaren.
```
