---
name: frontend-bouwen
description: >-
  Bouwt een UI voor een feature die daarom vraagt — niet elke feature heeft een scherm nodig,
  dit is dus geen verplichte stap zoals `feature-bouwen`. Kernidee: de mockup en de
  implementatie zijn dezelfde component, nooit een los ontwerpartefact dat kan verouderen.
  Fase 1 bouwt een volledig interactieve pagina met nepdata op de draaiende dev-server, vóór er
  ook maar een backend-regel geschreven is (ter visuele validatie, goedkoop te herzien); pas
  na goedkeuring loopt `feature-bouwen` (schema, keten, logica, tests); daarna pakt fase 2 de
  mockup-component op en vervangt de nepdata door een echte API-call. Gebruik deze skill bij
  "bouw een scherm voor X", "maak een UI voor deze feature", "laat me een mockup zien", of
  wanneer een story een UI-acceptatiecriterium bevat.
---

# Frontend bouwen — mockup vóór de backend, implementatie is dezelfde component

**Trigger:** een story vraagt een UI/scherm. Start direct ná `story-review`, vóór
`feature-bouwen`. De volgorde is: verhaal vastgelegd → mockup goedgekeurd → backend gebouwd →
echte data erin. Vraagt de feature geen UI: sla deze skill over en ga direct naar
`feature-bouwen`.

## Regels

1. **Fase 1 — interactieve mockup op de dev-server, vóór de backend.** Heeft het project meer
   dan één frontend-app, kies dan eerst de juiste frontend op basis van `stack-profiel.md`
   §Frontend(s). Bouw de pagina daarna als `<frontend>/app/mockup/<feature>/page.tsx` met
   hardgecodeerde nepdata. Geen live fetch; alle mutaties (aanmaken, bewerken, verwijderen)
   werken tegen lokale `useState` — de UI gedraagt zich volledig maar raakt de API niet. Zet
   een zichtbaar oranje "mockup — nepdata" badge rechtsboven op de pagina zodat het onderscheid
   met productie altijd zichtbaar is. Gebruik uitsluitend de al bestaande CSS-klassen en
   CSS-variabelen van het project (`.btn`, `.card`, `.tabel`, `rgb(var(--lint))`, etc.) zodat
   de mockup meteen in de juiste huisstijl valt. Geen gegenereerde types nodig in deze fase —
   nepdata heeft hard-getypeerde interfaces in het bestand zelf.

2. **Laat fase 1 zien vóór je doorgaat.** De mens opent de pagina op de draaiende dev-server
   (`http://localhost:<poort>/mockup/<feature>`), klikt er doorheen en geeft goedkeuring. Dit
   is het visuele validatiemoment — goedkoop te herzien, geen backend-code verspild. Pas na
   expliciete goedkeuring ga je verder. Commit fase 1 apart, zodat de git-geschiedenis toont
   hoe de component evolueerde. Dit is nog geen aflevering in de zin van `feature-bouwen`
   regel 9 (geen `/simplify`, geen Simplify-regel nodig op dit tussenpunt) — dat gebeurt pas
   één keer, aan het eind, over de volledige wijziging.

3. **`feature-bouwen` regel 1-6 (schema, keten, logica, tests) loopt hierna.** Na de
   goedkeuring van de mockup bouwt `feature-bouwen` de backend en genereert de TypeScript-types.
   Fase 2 hieronder wacht tot de keten klaar is.

4. **Fase 2 — promoveer de mockup naar zijn definitieve pad.** Verplaats
   `frontend/app/mockup/<feature>/page.tsx` naar het definitieve routepad (bv.
   `frontend/app/<feature>/page.tsx`). Vervang de hardgecodeerde nepdata door een echte
   `fetch`/API-call; importeer de types nu vanuit `frontend/generated/types.ts`. Verwijder de
   "mockup — nepdata" badge en de lokale mutatiefuncties. Verwijder de
   `/mockup/<feature>/`-map. Geen herbouw vanaf nul — alleen databron en pad veranderen.

5. **Geen apart design system optuigen vooraf.** Herbruikbare stijl/componenten (kleuren,
   knoppen, lay-outpatronen) pas extraheren zodra een tweede scherm hetzelfde patroon nodig
   heeft — duplicatie is pas een probleem ná de tweede onafhankelijke implementatie, net als
   `feature-bouwen` regel 8.

6. **Playwright-E2E-test, niet optioneel.**
   - **6a. Wanneer.** Bouw je een nieuwe of gewijzigde UI (d.w.z. je gebruikt `frontend-bouwen`
     sowieso al, zie de Trigger), dan hoort er een test bij in
     `<frontend>/tests/e2e/<naam>.spec.ts` die de UI echt in een browser bedient
     (`@playwright/test`) — niet een ad-hoc scriptje tijdens het bouwen dat na afloop wordt
     weggegooid (zie §Bekende valkuilen). Geen frontend-wijziging in deze PR: dan is deze regel
     niet van toepassing, net als de rest van deze skill.
   - **6b. Wat minimaal.** Het gelukkige pad (actie uitvoeren, resultaat zien zonder
     page-reload) en één foutpad (bv. een 409 van de server die als zichtbare foutmelding
     verschijnt, niet stil faalt). Draai de test lokaal (`npm run test:e2e`, met de dev-server en
     elke service die de UI aanroept al draaiend) vóórdat je aflevert. Twee onafhankelijke
     checks vangen dit daarna nog een keer op, geen van beide is zelfrapportage: CI
     (`check-frontend-e2e-coverage` in `.github/workflows/ci.yml`) faalt als de bron van een
     frontend wijzigt zonder een bijbehorende wijziging in diens `tests/e2e/`, en `code-review`
     regel 1 controleert het los daarvan nog een keer bij het lezen van de diff.

7. **Simplify en aflevering gebeuren niet hier.** Ná deze skill loopt `feature-bouwen` regel 9
   verder — één `/simplify`-ronde en één Simplify-regel in het commit-/PR-bericht voor de hele
   wijziging (backend + frontend samen), niet apart per fase.

## Mockup-structuur op een rij

```
frontend/app/mockup/
  <feature>/
    page.tsx        ← fase 1: nepdata + lokale state, badge zichtbaar
                    ← fase 2: verplaatst naar app/<feature>/page.tsx
```

Toegankelijk via `http://localhost:<poort>/mockup/<feature>` op de draaiende dev-server.
De `/mockup/`-map is alleen bedoeld voor fase-1-werkbestanden; na promotie is hij leeg en
kan hij verwijderd worden.

## Volgorde in de totale flow

```
story-review
  ↓
frontend-bouwen fase 1   ← interactieve mockup met nepdata (deze skill, regel 1-2)
  ↓ (goedkeuring mens)
feature-bouwen 1-6       ← schema, keten, logica, tests (aparte skill)
  ↓
frontend-bouwen fase 2   ← promoveer + echte data (deze skill, regel 4)
  ↓
feature-bouwen 9         ← /simplify, PR (aparte skill)
```

## Bekende valkuilen

- **Een tekstuele of ASCII-mockup die loskomt van de implementatie.** Een apart mockup-bestand
  (Figma, tekst, een los HTML-bestandje) kan niet worden geklikt, veroudert zodra de
  implementatie afwijkt en telt niet als visueel validatiemoment. Vandaar regel 1: de mockup is
  een echte React-component op de dev-server, niet een representatie ernaast.

- **Een handmatig testscript dat tijdens het bouwen wordt gedraaid en daarna weggegooid, voelt
  als verificatie maar laat geen herhaalbaar spoor achter.** Het werkt op het moment zelf, maar
  een latere wijziging aan diezelfde UI heeft niets om tegen te testen. Vandaar regel 6: de test
  hoort in de repo en in CI, niet als eenmalig scriptje ernaast.

## Wat dit niet oplost

- **Design system / herbruikbare component-bibliotheek** — pas relevant bij een tweede scherm
  (zie regel 5).
- **Mockup vóórdat er een story is** — er moet minimaal een goedgekeurde story zijn
  (`story-review` al doorlopen). Een mockup die de story zelf moet informeren, is een ander
  (nog niet uitgewerkt) scenario.
