---
name: pr-triage
description: >-
  Bepaalt bij een nieuwe of bijgewerkte pull request wat de volgende stap is: niets doen
  (draft/CI nog bezig), een review starten (`code-review`), openstaande blocking
  review-bevindingen laten verwerken door `feature-bouwen`, of mergen — en bij het mergen de
  in de PR-beschrijving genoteerde vervolgpunten overzetten naar `docs/vervolgpunten.md` en
  beide changelogs bijwerken met de classificatie die `code-review` (of, bij een mechanische
  dependency-bump, `dependency-updates`) al opleverde. Interpreteert de diff zelf niet opnieuw
  en fixt zelf geen code (dat is `feature-bouwen`'s taak, ook bij een fix naar aanleiding van
  review-bevindingen) — routeert, en verwerkt de output van andere skills naar vervolgpunten +
  changelogs. Slaat `code-review` alleen over bij een PR die `dependency-updates` al zichtbaar
  (niet alleen intern) als mechanisch classificeerde. Gebruik deze skill bij "wat moet er met
  deze PR gebeuren", "is deze klaar om te mergen", of elke keer dat een PR wordt aangemaakt of
  van een nieuwe commit voorzien. Niet voor de inhoudelijke review zelf (zie `code-review`) —
  deze skill beslist alleen *of* die nodig is.
---

# PR-triage — routeren, niet reviewen

**Trigger:** een pull request wordt aangemaakt, of krijgt een nieuwe commit.

## Regels

1. Bepaal de staat van de PR en handel dienovereenkomstig:

   | Staat | Actie |
   |---|---|
   | Draft, of CI-checks nog niet klaar | **Niets doen** — wachten. |
   | CI-checks bestaan wel maar hebben aantoonbaar niet gedraaid (workflow-parse-fout: 0s runs, geen jobs, "workflow file issue") of één of meer verplichte checks ontbreken volledig op de HEAD-SHA | **Blocker — fix CI eerst.** Zie regel 1a. |
   | CI-checks rood (jobs zijn wél gedraaid en daadwerkelijk gefaald) | **Blocker — fix eerst.** Schakel `feature-bouwen` in om de failing checks op te lossen; behandel dit als een blocking bevinding (rij 4). |
   | Dependency-bump mét een zichtbare `dependency-updates: mechanisch — <pakket> <van> → <naar>`-PR-comment (regel 2 van die skill), en CI is groen | **Mergen direct, `code-review` overslaan** — zie regel 2a. |
   | Laatste `code-review`-comment ("Review op `<sha>`: …") noemt niet de huidige HEAD-SHA van de PR, of zo'n comment ontbreekt | **`code-review`** starten. |
   | Laatste `code-review`-comment noemt de huidige HEAD-SHA, en meldt blocking bevindingen | **Schakel `feature-bouwen` in** om de blocking issues op te lossen — dit is feature-werk en volgt diens regels (de ene bron, generatieketen, logica in de routelaag, enz.), geen aparte ad-hoc aanpak vanuit deze skill. Na de fix opnieuw beoordelen (de nieuwe commit wijzigt de HEAD-SHA, dus de rij hierboven geldt weer). |
   | Laatste `code-review`-comment noemt de huidige HEAD-SHA zonder blocking bevindingen, Autonome merge = `nee`, nog geen goedkeuring ná die SHA | **Zet een PR-comment** en wacht — zie regel 2b. |
   | Laatste `code-review`-comment noemt de huidige HEAD-SHA zonder blocking bevindingen, en (Autonome merge = `ja`) of (Autonome merge = `nee` mét menselijke goedkeuring ná die SHA) | **Mergen**, zie regel 4 en 5. |

   **1a. "CI die niet draaide" ≠ "CI groen".** Een PR mag pas verder als de verplichte checks
   (zie `stack-profiel.md` §CI en `werkwijze/CLAUDE.md` §Codestandaard: `check-generated-types`,
   `check-frontend-e2e-coverage`, `check-python-style`, `check-ts-style`, testrun per service)
   ook daadwerkelijk gedraaid hebben op de huidige HEAD-SHA. Een ontbrekende check is even
   diskwalificerend als een gefaalde check — anders is been 1 van het Verificatie-principe
   (`werkwijze/CLAUDE.md` §Verificatie-principe) er niet, en leun je stilzwijgend op been 2
   (menselijke review) zonder dat iemand het door heeft. Concrete signalen:

   - een workflow-run duurt 0s en heeft 0 jobs (workflow-file-parse-fout)
   - `gh pr checks <nr>` toont "no checks reported"
   - `gh pr view <nr> --json statusCheckRollup` geeft `[]` terwijl de workflow-triggers wél
     matchen op de gewijzigde paden

   **Actie:** open een aparte fix-PR die CI werkend maakt (root-cause fixen, niet
   `continue-on-error: true` of check-uitzettingen), merg die eerst, en herstart de triage van
   déze PR op de nieuwe stand. Geen `code-review` en geen merge op de PR onder triage tot CI
   ook echt gedraaid heeft — één keer een groene ronde die "toevallig niet triggerde" is
   voldoende om drift onopgemerkt te laten binnenglippen.

2. **Nooit mergen zonder review, behalve de uitzondering hieronder.** Een documentatie-only of
   ogenschijnlijk triviale PR gaat eerst langs `code-review` — "dit is toch simpel" is te vaag
   om aan deze skill over te laten.

   **2a. De ene uitzondering: mechanische dependency-bumps.** Vereist een PR-comment of label
   van `dependency-updates` die de bump expliciet als mechanisch markeert (regel 2 van die
   skill) — een interne classificatie die nergens zichtbaar is, telt niet: zonder dat spoor is
   een getrieerde bump niet te onderscheiden van een nog onbekeken Dependabot-PR, en behandel je
   de PR als "nog geen review" (regel 1, rij 3). Zie `dependency-updates` regel 3 voor waarom
   een volledige `code-review` bij een écht mechanische bump weinig toevoegt. Nog steeds van
   toepassing: de Autonome-merge-instelling hieronder, en regel 4/5 — voor de
   changelog-classificatie gebruik je dan `dependency-updates`'s eigen samenvatting (regel 4 van
   die skill) in plaats van `code-review`'s output.

   **Check `CLAUDE.md` §Instellingen — Autonome merge** vóór je regel 4/5 uitvoert (ook bij
   regel 2a):
   - `ja` — merg direct zodra er niets blocking meer is.
   - `nee` — zie regel 2b.

   **2b. Autonome merge = `nee`: zet een concrete PR-comment, merg zelf niet.** Controleer eerst
   of er al een goedkeuring staat die ná de laatst gereviewde SHA is gegeven
   (`gh pr view <nr> --json reviewDecision,reviews`) — is die er, ga door naar regel 4/5. Is die
   er nog niet, en heb je voor déze SHA nog geen comment geplaatst, plaats er dan één:

   ```bash
   gh pr comment <nr> --body "Klaar om te mergen op <sha> — code-review vond niets blocking. Wacht op een menselijke goedkeuring (approve) voordat dit gemerged wordt."
   ```

   De SHA in de comment is het controleerbare spoor voor "al een keer gevraagd op deze stand"
   — een nieuwe commit ná deze comment betekent een nieuwe SHA, dus een nieuwe vraag is dan
   terecht.

3. Bij twijfel die de regels hierboven niet dekken: kies de staat die verder van mergen af
   staat. Nooit automatisch naar mergen bij twijfel.

4. **Vóór het mergen: verplaats vervolgpunten.** Staan er in de PR-beschrijving niet-blocking
   bevindingen genoteerd (uit `code-review`'s triagetabel), zet ze over naar
   `docs/vervolgpunten.md` met een verwijzing naar de PR en de story.

5. **Bij het mergen: werk beide changelogs bij met de classificatie en samenvattingen die
   `code-review` al opleverde** (regel 6 van die skill), of — bij een mechanische
   dependency-bump zonder `code-review` (regel 2a) — met `dependency-updates`'s eigen
   samenvatting (regel 4 van die skill). Interpreteer de diff hier zelf niet opnieuw, kopieer
   alleen:
   - `docs/changelog-technisch.md`: altijd een regel — `- <story/PR-titel> (PR #<nr>):
     <technische samenvatting>`.
   - `CHANGELOG.md`: **feature** → eigen regel met `code-review`'s niet-technische
     omschrijving. **bugfix** → vul de lopende "Bugfixes"-verzamelregel aan (aanmaken indien
     nodig). **qol** → vul de lopende "QoL updates"-verzamelregel aan. **technisch** → niet
     vermelden.

   **Commit regel 4 en 5 als een eigen, zichtbare commit op de PR-branch, vóór je mergt** — niet
   als een onzichtbare bijwerking van de merge-actie zelf. Zo staat de wijziging aan
   `docs/vervolgpunten.md` en de changelogs gewoon in de PR-geschiedenis, in plaats van iets dat
   achteraf nergens aan te herleiden is. Een technisch-geclassificeerde PR zonder vervolgpunten
   raakt alleen `docs/changelog-technisch.md`.
