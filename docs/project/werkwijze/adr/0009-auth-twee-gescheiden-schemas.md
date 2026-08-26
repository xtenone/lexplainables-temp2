# ADR-0009: Auth — twee gescheiden schema's

**Status:** geaccepteerd
**Datum:** 2026-08-12

## Context

Gebruikersauthenticatie (een mens die inlogt, met een sessie die dagen kan duren, mogelijk
tweefactorauthenticatie) en service-naar-service-/adminauthenticatie (een machine of beheerder
die een token gebruikt, met een andere levensduur en andere foutafhandelingseisen) hebben
wezenlijk verschillende eigenschappen. Eén gedeeld mechanisme voor beide dwingt een compromis af
dat voor geen van beide gevallen optimaal is.

## Beslissing

Gebruikersauthenticatie en service-/adminauthenticatie zijn twee volledig gescheiden
mechanismen — nooit hetzelfde token of dezelfde sessie voor beide doeleinden.

- **Gebruikersauthenticatie:** sessie-gebaseerd (bijvoorbeeld Auth.js), met optionele
  TOTP-tweefactorauthenticatie, rolgebonden (bijvoorbeeld `beheerder`/`analist`).
- **Service-/adminauthenticatie:** bearer-tokens met constante-tijd-vergelijking, fail-closed
  (geen toegang bij twijfel of fout) — voor elk administratief of service-naar-service-endpoint
  apart vereist, los van gebruikers-sessies.

## Consequenties

- Een lek van het ene mechanisme (bijvoorbeeld een gestolen gebruikers-sessie) geeft nooit
  toegang tot het andere (admin-bearer-tokens).
- Elk mechanisme kan onafhankelijk geroteerd of ingetrokken worden.
- Nadeel, bewust geaccepteerd: twee aparte implementaties om te onderhouden in plaats van één —
  geaccepteerd omdat de eisen wezenlijk verschillen (mens met sessie vs. machine/beheerder met
  token); een gedeeld mechanisme zou voor minstens één kant een verkeerde afweging zijn.
