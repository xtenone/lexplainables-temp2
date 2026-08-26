// Sorteren, filteren en groeperen voor het annotatie-overzicht.
//
// Bewust een eigen module zonder React: vitest draait node-env zonder DOM (`vitest.config.ts`), dus
// alleen pure helpers zijn te testen — dezelfde reden waarom `lib/selectie.ts` los staat van het
// documentpaneel. Het component eromheen doet alleen nog weergave.

import type { DocumentSamenvatting } from "./types";

export type Weergave = "te-doen" | "alles";

export const WEERGAVEN: { waarde: Weergave; label: string }[] = [
  { waarde: "te-doen", label: "Te doen" },
  { waarde: "alles", label: "Alles" },
];

export function weergaveUitParam(param: string | null | undefined): Weergave {
  return param === "alles" ? "alles" : "te-doen";
}

/** De vindplaats zoals hij in beeld komt: `art. 9 lid 2`. Werkt op zowel een samenvatting als een
 *  volledig document — beide dragen artikel en lid. */
export function vindplaatsLabel(d: { artikel: string; lid: string }): string {
  return `art. ${d.artikel}${d.lid ? ` lid ${d.lid}` : ""}`;
}

/** De naam waaronder een annotatie in beeld komt, met dezelfde terugval als de server hanteert:
 *  citeertitel → werkgebied (waar de wetnaam vroeger in stond) → bwbId. */
export function naamVan(d: { citeertitel?: string; werkgebied?: string; bwbId: string }): string {
  return d.citeertitel || d.werkgebied || d.bwbId;
}

/** Vraagt dit document nog werk? Alleen documenten die de jurist niet heeft afgerond tellen mee —
 *  afronden is een expliciete handeling, dus een afgerond document met open elementen is een
 *  bewuste keuze en geen restpost. */
export function isTeDoen(d: DocumentSamenvatting): boolean {
  return d.status === "in_review" && d.te_beoordelen > 0;
}

function aandacht(d: DocumentSamenvatting, niveau: string): number {
  return d.per_aandacht?.[niveau] ?? 0;
}

function tijd(d: DocumentSamenvatting): number {
  const t = d.updated ? Date.parse(d.updated) : NaN;
  return Number.isNaN(t) ? 0 : t;
}

/** Werkvoorraad-volgorde: rood eerst, dan geel, dan wat het langst stil ligt.
 *
 *  Niet op "meeste te beoordelen": een document met dertig open elementen zonder aandachtssignaal
 *  is routinewerk, terwijl één rood element een echte vraag is. De aandacht van de Critic weegt dus
 *  zwaarder dan de omvang. */
export function sorteerTeDoen(docs: DocumentSamenvatting[]): DocumentSamenvatting[] {
  return [...docs].sort(
    (a, b) =>
      aandacht(b, "rood") - aandacht(a, "rood") ||
      aandacht(b, "geel") - aandacht(a, "geel") ||
      tijd(a) - tijd(b),
  );
}

/** Alles-volgorde binnen een regeling: op artikel (numeriek, want '10' hoort ná '2') en dan lid. */
export function sorteerBinnenRegeling(docs: DocumentSamenvatting[]): DocumentSamenvatting[] {
  return [...docs].sort(
    (a, b) => nummer(a.artikel) - nummer(b.artikel) || nummer(a.lid) - nummer(b.lid),
  );
}

function nummer(waarde: string): number {
  const m = /\d+/.exec(waarde ?? "");
  return m ? Number(m[0]) : Number.MAX_SAFE_INTEGER;
}

export interface Regeling {
  naam: string;
  bwbId: string;
  documenten: DocumentSamenvatting[];
}

/** Groeperen op regeling: juristen denken in wetten, niet in losse documenten op datum.
 *  De groepen staan op naam; binnen een groep telt de artikelvolgorde. */
export function groepeerPerRegeling(docs: DocumentSamenvatting[]): Regeling[] {
  const perId = new Map<string, Regeling>();
  for (const d of docs) {
    const bestaand = perId.get(d.bwbId);
    if (bestaand) bestaand.documenten.push(d);
    else perId.set(d.bwbId, { naam: d.citeertitel || d.bwbId, bwbId: d.bwbId, documenten: [d] });
  }
  return [...perId.values()]
    .map((r) => ({ ...r, documenten: sorteerBinnenRegeling(r.documenten) }))
    .sort((a, b) => a.naam.localeCompare(b.naam, "nl"));
}

/** Zoeken op wat de jurist ziet: regelingnaam, bwbId, artikel/lid en werkgebied. Woord voor woord,
 *  zodat "zorgverzekering 43" werkt zonder dat de volgorde uitmaakt. */
export function zoek(docs: DocumentSamenvatting[], term: string): DocumentSamenvatting[] {
  const woorden = term.trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (woorden.length === 0) return docs;
  return docs.filter((d) => {
    const hooiberg = [
      d.citeertitel, d.werkgebied, d.bwbId, d.artikel, d.lid, vindplaatsLabel(d),
    ]
      .join(" ")
      .toLowerCase();
    return woorden.every((w) => hooiberg.includes(w));
  });
}

/** De JAS-kleurstrip: welk aandeel heeft elke klasse in dit document?
 *
 *  Terug in canonieke tabelvolgorde, zodat dezelfde verdeling er altijd hetzelfde uitziet en twee
 *  documenten naast elkaar te vergelijken zijn. */
export function kleurstrip(
  perKlasse: Record<string, number>,
  volgorde: readonly string[],
): { klasse: string; aantal: number }[] {
  const bekend = volgorde
    .filter((k) => (perKlasse?.[k] ?? 0) > 0)
    .map((k) => ({ klasse: k, aantal: perKlasse[k] }));
  // Klassen die niet in de canonieke lijst staan (oude data, drift) achteraan in plaats van weg:
  // een strip die stilzwijgend elementen weglaat liegt over de verdeling.
  const rest = Object.entries(perKlasse ?? {})
    .filter(([k, n]) => n > 0 && !volgorde.includes(k))
    .map(([klasse, aantal]) => ({ klasse, aantal }));
  return [...bekend, ...rest];
}
