// Rekenkern voor het zelf markeren van tekst: van een DOM-selectie naar een anker, en van een anker
// terug naar een positie in de brontekst.
//
// Bewust een pure module zonder DOM-afhankelijkheden: vitest draait hier in een node-omgeving, dus
// alleen zo is deze logica te testen. De DOM-wandeling zelf (een TreeWalker over de tekstknopen)
// blijft in het component; die geeft alleen lengtes door aan `offsetUit`.

import type { Anker } from "./types";

/** Hoeveel tekens context aan weerszijden in het anker wordt bewaard. */
export const CONTEXT_LENGTE = 48;

/** Vingerafdruk van de brontekst. Vertelt of de offsets in een anker nog over dezelfde tekst gaan;
 *  na een herimport kan de wettekst immers geschoven zijn.
 *
 *  Geen cryptografische hash nodig — dit beschermt niet tegen manipulatie maar tegen verwarring.
 *  Een 32-bits FNV-1a is daarvoor genoeg en werkt synchroon (SubtleCrypto is async). */
export function bronHash(bron: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < bron.length; i++) {
    h ^= bron.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0");
}

/** Absolute offset in de brontekst uit (index van de tekstknoop, offset daarbinnen).
 *  `lengtes` is de lengte van elke tekstknoop in documentvolgorde. */
export function offsetUit(lengtes: number[], knoopIndex: number, offsetInKnoop: number): number {
  let totaal = 0;
  for (let i = 0; i < knoopIndex && i < lengtes.length; i++) totaal += lengtes[i];
  return totaal + offsetInKnoop;
}

/** Trim witruimte en leestekens aan de randen van een selectie.
 *
 *  Een muisselectie pakt bijna altijd een spatie of punt te veel mee, en dat fragment moet
 *  letterlijk in de wettekst terug te vinden zijn — een meegesleepte punt maakt de markering
 *  onnodig broos. Geeft een leeg bereik terug als er niets bruikbaars overblijft. */
export function snapSelectie(bron: string, start: number, eind: number): { start: number; eind: number } {
  let s = Math.max(0, Math.min(start, bron.length));
  let e = Math.max(0, Math.min(eind, bron.length));
  if (s > e) [s, e] = [e, s];
  const rommel = (c: string) => /[\s.,;:]/.test(c);
  while (s < e && rommel(bron[s])) s++;
  while (e > s && rommel(bron[e - 1])) e--;
  return { start: s, eind: e };
}

/** Bouw het anker voor een selectie: positie + quote-context + vingerafdruk van de bron. */
export function maakAnker(bron: string, start: number, eind: number, lid = ""): Anker {
  return {
    lid,
    start,
    eind,
    voor: bron.slice(Math.max(0, start - CONTEXT_LENGTE), start),
    na: bron.slice(eind, eind + CONTEXT_LENGTE),
    bron_hash: bronHash(bron),
  };
}

/** Eén regel van de brontekst, met het lidnummer dat erbij hoort.
 *
 *  De regel is de tekst zoals hij in de bron staat — inclusief het "3. "-voorvoegsel — want daar zijn
 *  de offsets tegen berekend. Het lidnummer staat er los naast, want dat is niet uit de plek in de
 *  lijst af te leiden: zie `lidUitOffset`. */
export interface LidRegel {
  /** Het lidnummer zoals het in de wet staat ("2a"), of "" bij een artikel zonder genummerde leden. */
  lid: string;
  /** De regel zoals hij in de brontekst staat, inclusief het nummer-voorvoegsel. */
  regel: string;
}

/** In welk lid valt deze offset? `regels` in dezelfde volgorde als waarmee de bron is samengesteld
 *  (`bronVan`). Geeft het lidnummer terug, of "" als de offset erbuiten valt.
 *
 *  Let op het verschil met de plek in de lijst: dit gaf eerder `String(i + 1)` terug, en dat is alleen
 *  bij een compleet artikel met leden 1..n hetzelfde. Bij een op één lid afgebakend document levert de
 *  graaf alléén dat lid — dan is de index 0 en het lidnummer bijvoorbeeld 3 — en bij een ingevoegd lid
 *  (2a) lopen ze sowieso uiteen. Het lidnummer belandt in het element, het anker en het auditspoor,
 *  dus een gok is hier geen optie. */
export function lidUitOffset(regels: LidRegel[], start: number): string {
  let pos = 0;
  for (const r of regels) {
    const eind = pos + r.regel.length;
    if (start < eind) return r.lid;
    pos = eind + 2; // de "\n\n" tussen de regels
  }
  return "";
}

/** Zoek de positie van een fragment in de brontekst.
 *
 *  Drie stappen, van precies naar tolerant:
 *   1. het anker, als de bron-hash nog klopt en er op die plek echt dat fragment staat;
 *   2. alle voorkomens scoren op hoeveel omringende tekst overeenkomt met `voor`/`na` — zo landt een
 *      fragment dat drie keer in het artikel staat toch op de juiste plek, ook na een herimport;
 *   3. het eerste voorkomen dat nog vrij is.
 *
 *  `bezet` zijn de al toegewezen bereiken; overlap wordt overgeslagen. `-1` als er niets past. */
export function vindPositie(
  bron: string,
  fragment: string,
  anker: Anker | null | undefined,
  bezet: { start: number; eind: number }[],
): number {
  if (!fragment) return -1;
  const vrij = (idx: number) =>
    idx >= 0 && !bezet.some((b) => idx < b.eind && idx + fragment.length > b.start);

  if (anker && anker.bron_hash === bronHash(bron)) {
    if (bron.slice(anker.start, anker.eind) === fragment && vrij(anker.start)) return anker.start;
  }

  const kandidaten: number[] = [];
  for (let i = bron.indexOf(fragment); i !== -1; i = bron.indexOf(fragment, i + 1)) {
    if (vrij(i)) kandidaten.push(i);
  }
  if (kandidaten.length === 0) return -1;
  if (kandidaten.length === 1 || !anker) return kandidaten[0];

  let beste = kandidaten[0];
  let besteScore = -1;
  for (const idx of kandidaten) {
    const voor = bron.slice(Math.max(0, idx - CONTEXT_LENGTE), idx);
    const na = bron.slice(idx + fragment.length, idx + fragment.length + CONTEXT_LENGTE);
    const score = gemeenschappelijkeStaart(voor, anker.voor) + gemeenschappelijkeKop(na, anker.na);
    if (score > besteScore) {
      besteScore = score;
      beste = idx;
    }
  }
  return beste;
}

function gemeenschappelijkeStaart(a: string, b: string): number {
  let n = 0;
  while (n < a.length && n < b.length && a[a.length - 1 - n] === b[b.length - 1 - n]) n++;
  return n;
}

function gemeenschappelijkeKop(a: string, b: string): number {
  let n = 0;
  while (n < a.length && n < b.length && a[n] === b[n]) n++;
  return n;
}
