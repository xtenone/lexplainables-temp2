---
name: code-review
description: >-
  Toetst een pull request tegen `feature-bouwen` (en `frontend-bouwen` als de PR een UI raakt):
  correctheid, story-drift, en het verplichte Simplify-bewijs. Levert de classificatie die
  `pr-triage` gebruikt voor de changelogs. Gebruik deze skill bij "review deze PR", "check deze
  wijziging voordat we mergen", of wanneer `pr-triage` concludeert dat een review nodig is.
  Niet voor het bouwen van een nieuwe feature zelf (zie `feature-bouwen`), niet voor de vraag óf
  een PR sowieso al aan review toe is (zie `pr-triage`, die hieraan voorafgaat), en niet voor
  een projectbrede duplicatiezoektocht (zie `architectuur-audit`) — duplicatiedetectie is hier
  bewust alleen opportunistisch.
---

# Code review — contract-first werkwijze

**Trigger:** `pr-triage` heeft vastgesteld dat de PR nog geen review op de huidige stand heeft
gehad.

## Regels

1. Raakt de PR feature-code van een service of de bron van een frontend (welke mappen dat zijn:
   `stack-profiel.md` §Topologie en §Frontend(s))? Toets 'm dan tegen
   `feature-bouwen`/`frontend-bouwen`, regel voor regel — de bullets hieronder gelden alleen
   voor dat soort PR's, niet voor een documentatie- of CI-only wijziging:
   - Nieuwe tabellen/routes staan in een eigen `features/<naam>/`-map binnen één service, niet
     rechtstreeks in een verzamelbestand van die service (`feature-bouwen` regel 2).
   - Schema staat alleen op de "ene bron" van die service (zie `stack-profiel.md`) — geen los
     contract ernaast (`feature-bouwen` regel 3).
   - Gegenereerde bestanden zijn alleen gewijzigd via het generatiescript, niet met de hand — bij
     twijfel: script opnieuw draaien en diffen (`feature-bouwen` regel 4).
   - Businessregels en auth-checks staan in de routelaag, niet bij het schema (`feature-bouwen`
     regel 3 vs. 5).
   - Tests toetsen acceptatiecriteria en randgevallen, niet vorm die al door het schema
     gegarandeerd is (`feature-bouwen` regel 6).
   - Raakt de wijziging een tabel die al in productie bestaat: is er een echte migratie, niet
     alleen een "maak ontbrekende tabellen aan"-aanname (`feature-bouwen` regel 7)?
   - Herhaalt de PR een patroon uit een andere feature: staat de terugverwijzing "gebruikt
     `shared/<naam>.py`, zie daar" óf "gebruikt `<feature>.<module>.<functie>`, zie daar" in de
     story — beide vormen uit `feature-bouwen` regel 8 zijn geldig — of is er een duidelijke
     reden waarom het (nog) niet gedeeld is?
   - **Raakt de PR meer dan één service?** Dan is de vraag of dat terecht is (ADR-0002): een
     gedeelde import over een servicegrens heen is blocking, een expliciet contract + een
     genoteerde deploy-volgorde niet. Eén story die twee services tegelijk moet wijzigen is op
     zichzelf een signaal, geen fout.
   - **Raakt de PR frontend-bron?** Staat er een Playwright-E2E-test bij in de `tests/e2e/`-map
     van diezelfde frontend (`frontend-bouwen` regel 6)? CI controleert de aanwezigheid via
     `check-frontend-e2e-coverage`, maar niet of de test zinvol is — dit is de kwalitatieve check.
   - **Voegt de PR een nieuwe feature-map, een nieuwe service of de eerste frontend toe?** Dan
     hoort `docs/architectuur/c4-model.md` mee te veranderen (de Component-sectie bij een nieuwe
     feature, de Container-sectie bij een nieuwe service of frontend). Geen wijziging aan dat
     bestand terwijl de structuur wél verandert: vervolgpunt, niet per se blocking (zie de
     triagetabel in regel 5).
   - Staat er een geldige `Simplify:`-regel (de vier vormen uit `feature-bouwen` regel 9) in het
     commit-bericht of de PR-beschrijving? Zonder een van de vier is er geen controleerbaar
     bewijs dat die stap is afgehandeld — behandel dat als een onvolledige PR, ongeacht hoe
     klein de wijziging lijkt (klein-lijkende wijzigingen zijn precies waar dit soort stappen
     het makkelijkst wegvallen, zie `feature-bouwen` §Bekende valkuilen).

2. **Story-drift** — alleen relevant voor PR's die onder regel 1 vallen. Controleer dat
   `docs/stories/<nummer>-<naam>.md` overeenkomt met wat de code doet. Ontbreekt de story bij
   zo'n PR, dan is de PR niet compleet.

3. Generieke correctheid en veiligheid: input-validatie voorbij het schema, auth op nieuwe
   endpoints, geen secrets in code of migraties.

4. Duplicatie-detectie binnen deze skill is **opportunistisch**, net als `feature-bouwen`
   regel 8: valt je tijdens het lezen van deze PR iets op, meld het. Doorzoek er niet apart het
   project voor — dat is `architectuur-audit`.

5. Rapporteer bevindingen en triage elk ervan vóór je de merge blokkeert of vrijgeeft:

   | Type bevinding | Actie |
   |---|---|
   | Overtreding van een bullet in regel 1 | Blocking — altijd verwerken. |
   | Correctheid of veiligheid, ook als geen regel het letterlijk benoemt (bug, security-issue, auth-gat) | Blocking. |
   | Story-drift (regel 2) | Blocking tot story of code is aangepast. |
   | Stijl, smaak, of een verbetering die geen regel schendt en geen bug is | Niet blocking — expliciet als vervolgpunt noteren (in de PR-beschrijving), niet stilzwijgend laten vallen. |
   | Bevinding buiten de scope van deze diff (pre-existing probleem, ongerelateerd bestand) | Niet in deze PR fixen — noteer als vervolgpunt in de PR-beschrijving, zelfde mechanisme als de rij hierboven. Geen los kanaal ernaast. |
   | Ongeverifieerde bevinding (aanname, niet tegen de code getoetst) | Eerst verifiëren voordat je 'm als blocking behandelt. |
   | Performance/schaalbaarheid (bv. een N+1-query, een endpoint dat onder realistische load traag wordt) | Blocking als het aantoonbaar productiegedrag raakt, anders vervolgpunt. |
   | Valt buiten alle rijen hierboven | Beoordeel op impact op correct gedrag in productie, niet op categorie — bij twijfel blocking. |

   Blokkeer de merge dus nooit op smaak of stijlvoorkeur — alleen op de blocking-rijen hierboven.

   Sluit de review af met een PR-comment die vastlegt tegen welke commit-SHA je hebt
   gereviewd en het resultaat (`Review op <sha>: N blocking, M vervolgpunten`). Zonder dat spoor
   kan `pr-triage` niet objectief vaststellen of de huidige stand van de PR al gereviewd is
   (regel 1 van die skill) — het zou anders op giswerk of eindeloos herhalen neerkomen.

6. **Classificeer de wijziging voor de changelogs** (`pr-triage` gebruikt dit bij het mergen,
   zonder de diff zelf opnieuw te hoeven interpreteren):
   - Type: **feature** (nieuwe functionaliteit/zichtbare gedragswijziging), **bugfix**
     (gebruiker zag iets zichtbaar kapot), **qol** (merkbare kleine verbetering zonder nieuwe
     functionaliteit), of **technisch** (geen zichtbaar effect — refactor, dependency-bump,
     infra).
   - Lever altijd een korte technische samenvatting (voor `docs/changelog-technisch.md`).
   - Bij **feature**: lever ook een korte, niet-technische omschrijving (voor `CHANGELOG.md`).
