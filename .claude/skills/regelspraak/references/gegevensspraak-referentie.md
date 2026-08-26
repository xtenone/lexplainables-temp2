# GegevensSpraak-referentie — het objectmodel

De exacte syntax van GegevensSpraak (RegelSpraak-specificatie v2.3.0, hoofdstuk 3). RegelSpraak
*gebruikt* deze gegevens, dus specificeer ze eerst. Gebruik **uitsluitend** de taalpatronen
hieronder; verzin geen syntax. Voorbeelden komen uit de TOKA-casus van de spec.

> **Notatie.** `<…>` is een variabel deel; `[…]` is optioneel; `(a | b)` is een keuze. In de
> echte regel staan tussen variabele delen spaties (de syntaxregels laten die weg voor de
> leesbaarheid).

## Inhoud
1. [Objecttypen](#1-objecttypen)
2. [Attributen](#2-attributen)
3. [Standaarddatatypes](#3-standaarddatatypes)
4. [Domeinen](#4-domeinen)
5. [Kenmerken](#5-kenmerken)
6. [Dimensies](#6-dimensies)
7. [Eenheden en eenheidssystemen](#7-eenheden-en-eenheidssystemen)
8. [Tijdlijnen](#8-tijdlijnen)
9. [Parameters](#9-parameters)
10. [Feittypen en rollen](#10-feittypen-en-rollen)
11. [Dagsoort](#11-dagsoort)

---

## 1. Objecttypen

Een objecttype definieert een groep gelijksoortige objecten. Objecten in RegelSpraak zijn altijd
**instanties** van een objecttype. Een objecttypedefinitie begint met `Objecttype`, gevolgd door
een **naamwoord** (lidwoord + zelfstandig naamwoord), eventueel de **meervoudsvorm** tussen
haakjes met `mv:`, en eventueel `(bezield)` voor een levend wezen.

```
Objecttype de Natuurlijk persoon (mv: Natuurlijke personen) (bezield)
```

- **Bezield** betekent: een objecttype met een ziel (levend wezen). Naar bezielde objecttypen
  kun je in regels verwijzen met het voornaamwoord `hij` en het bezittelijk voornaamwoord `zijn`.
- **Extensie** (optioneel, voor overzicht): eigenschappen in een apart deel clusteren met
  `Extensie van objecttype de <naamwoord>`.

Syntax:
```
"Objecttype" <naamwoord> ["(bezield)"]
<naamwoord> ::= [ <bepaaldlidwoord> ] <naam> [ "(mv:" <meervoudsvorm> ")" ]
<bepaaldlidwoord> ::= "de" | "het"
```

## 2. Attributen

Een **attribuut** is een gegeven van een objecttype dat een concrete waarde kan hebben. Een
attribuut wordt aangeduid met een naamwoord + een **datatype** (of domein). Een attribuut zonder
waarde heeft een **lege waarde**.

```
Objecttype de Natuurlijk persoon (mv: Natuurlijke personen) (bezield)
  het identificatienummer                     Numeriek (positief geheel getal);
  de geboortedatum                            Datum in dagen;
  de leeftijd                                 Numeriek (niet-negatief geheel getal) met eenheid jr;
  de te betalen belasting                     Bedrag;
```

Syntax (versimpeld; `gedimensioneerd met` / `<tijdlijn>` zijn optioneel maar niet samen):
```
<attribuut> ::= <naamwoord>  (<datatype> | <domeinnaam>) ["gedimensioneerd met" <dimensienaam>] [<tijdlijn>] ";"
```

Elke attribuutregel eindigt met `;`. Een domein (zie §4) gebruik je als datatype door zijn naam
te noemen (in RegelSpraak *cursief* weergegeven, bv. `Bedrag`).

## 3. Standaarddatatypes

Er zijn **vijf** standaarddatatypes: Numeriek, Tekst, Boolean, Datum-tijd, Percentage.

### Numeriek
Rationele getallen, al dan niet met een eenheid. **Verplichte** specificatie van de precisie:
- `geheel getal` (0 decimalen),
- `getal met x decimalen` (x verplicht, bv. `getal met 2 decimalen`),
- `getal` (onbeperkt aantal decimalen).

**Optionele** bereikspecificatie: `negatief`, `positief`, `niet-negatief` (= positief inclusief 0).
```
de leeftijd            Numeriek (niet-negatief geheel getal);
het identificatienummer  Numeriek (positief geheel getal);
de afstand tot bestemming Numeriek (geheel getal);
```

### Tekst
Letters/tekens uit Unicode. Een tekstwaarde staat altijd tussen dubbele aanhalingstekens
(`"Amsterdam Schiphol"`). Geen verdere beperking.
```
het burgerservicenummer  Tekst;
```

### Boolean
Precies twee waarden: `waar` en `onwaar`. Geen verdere beperking. (Geef de voorkeur aan een
*kenmerk* boven een Boolean-attribuut waar dat kan — zie §5.)
```
bereikbaar per trein  Boolean;
```

### Datum-tijd
Voor datums/tijdstippen. Eén nadere beperking, verplicht: `in dagen` (bv. 12-03-2023) of
`in millisecondes` (bv. 12-03-2023 11:34:42.679).
```
de geboortedatum                  Datum in dagen;
de verwachte datum-tijd van vertrek  Datum en tijd in millisecondes;
```

### Percentage
Een gespecialiseerd Numeriek datatype: ook hier een **verplichte** precisie-beperking, optioneel
een bereik. Standaardeenheid `%`, eventueel nader (bv. `%/jaar`).
```
Parameter het percentage reisduur tweede schijf : Percentage (geheel getal)
```

## 4. Domeinen

Een **domein** geeft een vaak voorkomende waardesoort één eenduidige, herbruikbare definitie. Een
domein is gebaseerd op een standaarddatatype (niet Boolean), al dan niet met eenheid, óf op een
**enumeratie** (een limitatieve lijst waarden).

Op basis van een standaarddatatype:
```
Domein Bedrag is van het type Numeriek (getal met 2 decimalen) met eenheid €
```

Op basis van een enumeratie (een attribuut met dit domein mag alleen een waarde uit de lijst):
```
Domein Luchthavens is van het type Enumeratie
  'Amsterdam Schiphol'
  'Groningen Eelde'
  'Parijs Charles de Gaulle'
  'Londen Heathrow'
```
Enumeratiewaarden staan tussen **enkele** aanhalingstekens.

Syntax:
```
<domeindefinitie> ::= "Domein" <domeinnaam> "is van het type" (<datatype> | <enumeratiespecificatie>)
<enumeratiespecificatie> ::= "Enumeratie" \n (\t <enumeratiewaarde> \n)+
```

## 5. Kenmerken

Een **kenmerk** is een eigenschap die een object wél of niet heeft. Default heeft een kenmerk een
object *niet* (onwaar); alleen via een **kenmerktoekenning** (zie de regels-referentie) wordt het
waar. Anders dan een Boolean-attribuut test je bij een kenmerk op *aanwezig zijn*, niet op een
waarde. Drie soorten:

1. **Bijvoeglijk** — je spreekt erover met het werkwoord "zijn": *Natuurlijk persoon is
   minderjarig*. Specificatie met `is` vóór het naamwoord:
   ```
   is minderjarig  kenmerk (bijvoeglijk);
   ```
2. **Bezittelijk** — je spreekt erover met "hebben": *Natuurlijk persoon heeft recht op
   duurzaamheidskorting*. Specificatie met lidwoord + `kenmerk (bezittelijk)`:
   ```
   het recht op duurzaamheidskorting  kenmerk (bezittelijk);
   ```
3. **Overig** (noch bijvoeglijk, noch bezittelijk) — "zijn" + lidwoord: *Natuurlijk persoon is
   een passagier van 18 tot en met 24 jaar*:
   ```
   de passagier van 18 tot en met 24 jaar  kenmerk;
   ```

In één objecttype samen:
```
Objecttype de Natuurlijk persoon (mv: Natuurlijke personen) (bezield)
  is minderjarig                     kenmerk (bijvoeglijk);
  het recht op duurzaamheidskorting  kenmerk (bezittelijk);
  de passagier van 18 tot en met 24 jaar  kenmerk;
```

## 6. Dimensies

Een **dimensie** laat een attribuut op hetzelfde moment meerdere waarden hebben (bv. een inkomen
per jaar, of bruto/netto). Een dimensie bestaat uit een geordende verzameling **labels**.

```
Dimensie de jaardimensie, bestaande uit de jaardimensies (na het attribuut met voorzetsel van):
  1. vorig jaar
  2. huidig jaar

Dimensie de brutonettodimensie, bestaande uit de brutonettodimensies (voor het attribuut zonder voorzetsel):
  bruto
  netto
```

Het attribuut koppelt de dimensie(s) met `gedimensioneerd met`:
```
het inkomen  Numeriek (geheel getal) gedimensioneerd met jaardimensie en brutonettodimensie;
```
In regels verwijs je dan naar bv. *het bruto inkomen van vorig jaar*. Verwijzing kan **na het
attribuut met voorzetsel** (van/in/voor/over/op/bij/uit) of **vóór het attribuut** (label als
bijvoeglijk naamwoord).

## 7. Eenheden en eenheidssystemen

Bij Numeriek (en Percentage) kan een **eenheid** horen. Een eenheid hoort bij een
**eenheidssysteem**: een naamwoord, eventueel afkorting/symbool, en eventueel een
**omrekenspecificatie** (omrekenfactor naar een andere basiseenheid uit hetzelfde systeem).

```
Eenheidssysteem Valuta
  de euro (mv: euros) EUR €
```
Een eenheid koppel je aan een attribuut/parameter met `met eenheid`:
```
de te betalen belasting  Bedrag met eenheid euro;
de snelheid              Numeriek (getal) met eenheid km/u
de versnelling           Numeriek (getal) met eenheid m/s^2
```
**Samengestelde** eenheden via `/` (deling) of machten (`^`). Omrekenfactoren (kleinste eenheid
eerst):
```
Eenheidssysteem afstand
  de millimeter (mv: millimeters)  mm  = 1/1000 m
  de centimeter (mv: centimeters)  cm  = 1/100 m
  de meter (mv: meters)            m
  de kilometer (mv: kilometers)    km  = 1000 m
```
**Standaard** eenheidssystemen die deel zijn van GegevensSpraak: **Valuta** (ISO-4217, geen
omrekenfactoren) en **Tijd** (ms, s, minuut, u, dg, wk, mnd, kw, jr).

## 8. Tijdlijnen

Attributen, kenmerken en parameters kunnen **tijdsafhankelijk** zijn: hun waarde *kan* in de tijd
veranderen. Voeg een tijdlijn toe aan de declaratie. Mogelijkheden:

- **Enkelvoudige tijdseenheid** (gregoriaanse kalender): dag, maand, kwartaal, jaar.
  ```
  de te betalen belasting  Bedrag voor elk jaar;
  het recht op duurzaamheidskorting kenmerk (bezittelijk) voor elke dag;
  ```
- **Met afwijkend vast startpunt:**
  ```
  de te betalen belasting  Bedrag voor elk jaar startend op dag 12 van maand 2;
  ```
- **Meervoudige tijdseenheden** (veelvouden; startpunt verplicht, behalve als het veelvoud exact
  in een kalenderjaar past):
  ```
  de te betalen belasting  Bedrag voor elke 5 maanden startend op 9-3-2025;
  ```
- **Variabel startpunt** (apart gedeclareerd in het objectmodel; startpunt via een
  Startpuntbepalingsregel):
  ```
  Tijdlijn de periode van een kwartaal vanaf de geboortedatum heeft tijdvakken van een kwartaal met variabel startpunt;
  de te betalen belasting  Bedrag voor elke periode van een kwartaal vanaf de geboortedatum;
  ```

De kleinst mogelijke tijdseenheid is de dag.

## 9. Parameters

Een **parameter** is een globaal gegeven dat niet bij één specifiek objecttype hoort en waarvan de
waarde binnen de context bekend is (bv. een tarief of een drempel). Een parameter heeft net als een
attribuut een datatype (of domein), eventueel met eenheid.

```
Parameter de korting bij gebruik niet-fossiele brandstof : Bedrag
Parameter de volwassenleeftijd : Numeriek (niet-negatief geheel getal) met eenheid jr
```
Syntax:
```
<parameterdefinitie> ::= "Parameter" <bepaaldlidwoord> <parameternaam> ":" (<datatype> | <domeinnaam>) [<tijdlijn>]
```
Gebruik parameters om te voorkomen dat vaste waarden ("harde" cijfers) in de regels staan — zo
blijven ze beheerbaar zonder de regel aan te passen.

## 10. Feittypen en rollen

Een **feittype** legt een relatie vast tussen objecttypen via **rollen**. Een rol wordt
**ingevuld** door instanties van het bijbehorende objecttype; zo ontstaat een relatie. Een rol is
**enkelvoudig** (`één`) of **meervoudig** (`meerdere`).

```
Feittype Vlucht van natuurlijke personen
  de reis       Vlucht
  de passagier  Natuurlijk persoon
Eén reis betreft de verplaatsing van meerdere passagiers
```
De laatste regel is de **relatiebeschrijving**: `Eén/meerdere <rolnaam> <beschrijving>
één/meerdere <rolnaam>`.

**Wederkerig** feittype (beide objecttypen vervullen dezelfde rol; alleen met enkelvoudige rol):
```
Wederkerig feittype Partnerrelatie
  de partner  Natuurlijk persoon
Eén partner heeft één partner
```

## 11. Dagsoort

Een **dagsoort** definieert een soort dag (Nieuwjaarsdag, Paasdag, …) die je in regels gebruikt om
te controleren of een datum een feestdag is, of om feestdagen over te slaan. Specificatie met
lidwoord + naam + meervoud:
```
Dagsoort de kerstdag (mv: kerstdagen)
```
Wanneer een datum van die dagsoort *is*, leg je vast in een **Dagsoortdefinitie**-regel (zie de
regels-referentie, §9.8 van de spec).
