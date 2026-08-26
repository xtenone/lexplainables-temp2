---
name: dependency-updates
description: >-
  Verwerkt open Dependabot-PR's/-alerts op een vaste cadans: triage mechanisch (patch/minor)
  versus risico (major, of een advisory die breaking changes noemt). Mechanische bumps mag
  `pr-triage` direct mergen zonder `code-review` (regel 2a van die skill) zodra CI groen is;
  risico-bumps doorlopen de volledige cyclus, ná akkoord van de gebruiker. Gebruik deze skill
  bij "verwerk de dependency-updates", "wat staat er open in Dependabot", "bump de deps", of op
  vaste cadans (bv. wekelijks). Niet voor featurewerk (zie `feature-bouwen`) en niet voor
  architecturale duplicatie/cohesie (zie `architectuur-audit`) — uitsluitend het bijhouden van
  dependency-versies.
---

# Dependency-updates

**Trigger:** vaste cadans (bijvoorbeeld wekelijks), of een nieuwe Dependabot-PR.

## Regels

1. Haal de open Dependabot-PR's en -alerts op (`gh pr list --author app/dependabot`,
   `gh api repos/<owner>/<repo>/dependabot/alerts?state=open`). Groepeer per **manifest**, niet
   per ecosysteem: elke service heeft zijn eigen manifest en zijn eigen lockfile, plus de
   frontend(s) en `.github/workflows/*.yml`. Zoek die lijst op in `stack-profiel.md` §Topologie
   en §Frontend(s) in plaats van 'm aan te nemen — een gemist manifest ziet er in de rapportage
   (regel 5) uit als "geen openstaande bumps".

   Dezelfde bump in twee services is twee losse bumps: ze zijn onafhankelijk deploybaar
   (ADR-0002), dus ze hoeven niet in dezelfde PR of dezelfde week.

2. **Triage per bump:**
   - Patch/minor binnen dezelfde major → **mechanisch**. Kan zonder tussenkomst door naar
     regel 3.
   - Major, of de advisory/release-notes noemen breaking changes → **risico**. Vat de
     changelog/upgrade-guide samen en vraag de gebruiker om akkoord vóór je verder gaat.
   - Meerdere bumps in één groeps-PR (bv. een dev-dependency-groep) → behandel ze los; is
     alles in de groep mechanisch, dan mag de PR als geheel door.

3. **Mechanisch → zet een zichtbare markering op de PR, dan mag `pr-triage` `code-review`
   overslaan** (regel 2a van `pr-triage`), mits CI (`.github/workflows/ci.yml`) groen is — dat
   blijft hard, ook voor een mechanische bump. Er is dan geen schema/businesslogica/story om
   tegen te toetsen, dus een volledige review voegt niets toe; de tests zijn de verificatie.

   De markering moet zichtbaar op de PR staan, niet alleen een interne beslissing van deze
   sessie — `pr-triage` kan anders niet onderscheiden of een bump al getrieerd is:

   ```bash
   gh pr comment <nr> --body "dependency-updates: mechanisch — <pakket> <van> → <naar>"
   ```

   **Risico → wél de volledige cyclus**, ná akkoord van de gebruiker: `pr-triage` → `code-review`
   → eventueel terug naar `feature-bouwen` als de bump een codewijziging vergt (bijvoorbeeld
   een verplaatste import na een major). Geen kortsluiting hier — de bump zelf is per definitie
   niet objectief "simpel" gebleken.

4. **Classificeer zelf voor de changelogs** bij een mechanische bump (er is geen `code-review`
   om dit te doen, zie diens regel 6 voor het formaat dat `pr-triage` verwacht): type
   **technisch** (komt dus alleen in `docs/changelog-technisch.md`), plus een technische
   samenvatting (`<pakket> <van> → <naar>`). Bij een risico-bump met codewijziging classificeert
   `code-review` gewoon zelf, net als bij featurewerk.

5. Rapporteer na afloop welke alerts sluiten en welke Dependabot-PR's zijn overgeslagen (en
   waarom) — nooit stil een risico-bump negeren.
