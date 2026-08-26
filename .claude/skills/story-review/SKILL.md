---
name: story-review
description: >-
  Toetst een user story in docs/stories/ op volledigheid vóórdat `feature-bouwen` begint:
  concrete/testbare acceptatiecriteria, expliciete schemabeslissing, edge cases, auth/rollen,
  een terechte terugverwijzing bij verwijzingen naar gedeelde logica, en een gekozen
  prioriteit. Vult onduidelijkheden zelf aan waar dat eenduidig uit de story of bestaande code
  volgt, en stelt anders een concrete vraag aan de gebruiker. Kent aan het eind ook story
  points toe (1-5). Gebruik deze skill bij "check deze story", "is deze story
  compleet", "controleer de requirements", "vul deze story aan", of elke keer dat een nieuwe
  story geschreven is en nog niet gebouwd wordt. Niet voor het beoordelen van geschreven code
  tegen een story (zie `code-review`) en niet voor het bouwen zelf (zie `feature-bouwen`) — dit
  is uitsluitend de story zelf, vóór er code bestaat.
---

# Story-review — requirements-check vóór het bouwen

**Trigger:** een nieuwe of gewijzigde user story in `docs/stories/`, vóór `feature-bouwen`
eraan begint.

## Regels

1. Lees de story volledig. Toets tegen deze checklist:
   - **Acceptatiecriteria zijn concreet en testbaar** — elk criterium moet direct te
     vertalen zijn naar een gedragstest (`feature-bouwen` regel 6). Een criterium als "het
     werkt intuïtief" is geen acceptatiecriterium.
   - **Schemabeslissing is expliciet** — velden en types staan benoemd, niet impliciet
     ("een analyse heeft de gebruikelijke velden") (`feature-bouwen` regel 1).
   - **De service is benoemd** — bij welke service hoort deze feature (`stack-profiel.md`
     §Topologie, `feature-bouwen` regel 2)? Volgt dat niet eenduidig uit de story, dan is dat
     een onduidelijkheid. Raakt de story er meer dan één, dan hoort in de story te staan wat
     elke service doet en hoe ze elkaar aanroepen — twee services stilzwijgend in één story
     stoppen is precies waar een contract tussen services vergeten wordt (ADR-0002).
   - **Edge cases zijn benoemd** — wat gebeurt er bij ongeldige invoer, een actie op iets dat
     niet bestaat, of een actie die al is uitgevoerd (dubbel inleveren, dubbel aanmaken)? Als
     de story een regel impliceert zonder 'm uit te spreken, is dat een onduidelijkheid.
   - **Auth/rollen zijn benoemd** — wie mag deze actie uitvoeren? Ontbreekt dit bij een
     muterend endpoint, dan is dat een onduidelijkheid, geen aanname om zelf te maken.
   - **Terugverwijzingen naar gedeelde logica zijn terecht** — verwijst de story naar
     `shared/<naam>.py` of naar `<feature>.<module>.<functie>` (`feature-bouwen` regel 8),
     verifieer dat die module/functie al bestaat, van toepassing is, en in dezelfde service
     staat — een terugverwijzing over een servicegrens heen kan niet (ADR-0002). Een verwijzing naar iets
     dat nog niet bestaat na precies één eerdere implementatie is zelf een onduidelijkheid, niet
     een vooruitziende blik om stilzwijgend te honoreren.
   - **Prioriteit is expliciet gekozen** (`none` / `low` / `medium` / `high`) — staat het veld
     nog op `none` (de template-startwaarde) of ontbreekt het helemaal? Dat is een
     onduidelijkheid als elke andere: vul aan volgens regel 2, met `medium` als concreet
     voorstel. Geen vraag aan de gebruiker nodig — `none` is een startwaarde, geen bewuste
     eindkeuze die je moet respecteren.

2. Voor elke onduidelijkheid: probeer 'm eerst zelf op te lossen vanuit de rest van de story of
   een bestaande, vergelijkbare feature. Vul aan met een concreet voorstel en markeer dat
   duidelijk als aanvulling.

3. Is er geen eenduidig antwoord af te leiden: stel een concrete, gesloten vraag aan de
   gebruiker (opties of een duidelijk ja/nee, geen open "wat wil je hier?"). Doorloop de
   volledige checklist eerst voordat je vragen stelt — verzamel alle onduidelijkheden in één
   ronde in plaats van iteratief.

4. Rond pas af zodra er geen open vragen meer zijn, of de gebruiker heeft expliciet
   geaccepteerd dat een gevonden randgeval later wordt opgepakt (leg dat expliciet vast in de
   story, niet stilzwijgend laten vallen).

5. **Ken story points toe (1-5)** — een schatting, geen harde regel, direct op basis van deze
   rubric (geen vergelijking met eerdere stories nodig — dit is een absolute indeling, geen
   relatieve zoals klassieke Fibonacci-story-points, die pas betekenis krijgen bij een hele
   backlog om tegen af te zetten):

   | Punten | Betekenis |
   |---|---|
   | 1 | Eén entiteit, geen businessregel, geen edge cases. |
   | 2 | Eén of twee entiteiten, één eenvoudige regel. |
   | 3 | Meerdere entiteiten, óf één niet-triviale businessregel met edge cases. |
   | 4 | Meerdere entiteiten mét meerdere businessregels, of auth/rollen erbij. |
   | 5 | Meerdere entiteiten, meerdere regels, auth, én/of gedeelde logica — raakt meer dan één feature. |

   Dit is jouw eigen inschatting; vraag de gebruiker hier niet naar zoals bij een echte
   onduidelijkheid (regel 2-3) — de gebruiker kan de punten altijd achteraf zelf bijstellen.

6. Werk de story zelf bij met de aanvullingen, antwoorden, prioriteit en story points — de
   story blijft de bron van waarheid voor `feature-bouwen`, niet een los reviewverslag ernaast.
