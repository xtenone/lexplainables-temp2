// Pure filterlogica voor de artikel-combobox, los van React zodat ze unit-testbaar is.

import type { ArtikelChoice } from "./types";

/** Ziet de invoer eruit als een BWB-id? Dan is een structuur-lookup zinvol. */
export function isBwbId(s: string): boolean {
  return /^BWB[RVW]\d+$/i.test(s.trim());
}

/**
 * Filter + rangschik artikelen op de getypte query: exacte match eerst, dan nummers die
 * ermee beginnen, dan nummers die de query bevatten (alles case-insensitief). Binnen elke
 * groep blijft de documentvolgorde staan. Lege query → de eerste `max` in documentvolgorde.
 */
export function filterArtikelen(items: ArtikelChoice[], query: string, max = 50): ArtikelChoice[] {
  const q = query.trim().toLowerCase();
  if (!q) return items.slice(0, max);
  const exact: ArtikelChoice[] = [];
  const begintMet: ArtikelChoice[] = [];
  const bevat: ArtikelChoice[] = [];
  for (const item of items) {
    const nr = item.artikel.toLowerCase();
    if (nr === q) exact.push(item);
    else if (nr.startsWith(q)) begintMet.push(item);
    else if (nr.includes(q)) bevat.push(item);
  }
  return [...exact, ...begintMet, ...bevat].slice(0, max);
}

/** Aantal treffers zónder cap — voor de "… nog N artikelen"-voetregel. */
export function telTreffers(items: ArtikelChoice[], query: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return items.length;
  let n = 0;
  for (const item of items) if (item.artikel.toLowerCase().includes(q)) n++;
  return n;
}

/** Staat het getypte artikelnummer (exact, case-insensitief) in de lijst? */
export function bestaatArtikel(items: ArtikelChoice[], artikel: string): boolean {
  const a = artikel.trim().toLowerCase();
  return a !== "" && items.some((i) => i.artikel.toLowerCase() === a);
}
