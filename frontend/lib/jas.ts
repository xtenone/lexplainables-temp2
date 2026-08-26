// De dertien JAS-klassen (zie references/jas-klassen-referentie.md) met een vaste,
// onderscheidende badge-kleur per klasse. Onbekende klassen vallen terug op "neutraal".

export const JAS_KLASSEN = [
  "Rechtssubject",
  "Rechtsobject",
  "Rechtsbetrekking",
  "Rechtsfeit",
  "Voorwaarde",
  "Afleidingsregel",
  "Variabele en variabelewaarde",
  "Parameter en parameterwaarde",
  "Operator",
  "Tijdsaanduiding",
  "Plaatsaanduiding",
  "Delegatiebevoegdheid en delegatie-invulling",
  "Brondefinitie",
] as const;

// Tailwind-klassen per JAS-klasse (achtergrond + tekst + rand). De achtergrondkleuren zijn
// de exacte labelkleuren uit de officiële JAS-tabel (docs/wa-table.png), per pixel gesampled;
// de rand is dezelfde kleur ~22% donkerder. Tekst is text-ink (#1A1A1A, ≥ 5,4:1 op elke tint).
// Samengevoegde klassen nemen de hoofdkleur uit de tabel (Variabele / Parameter / Delegatiebevoegdheid).
const KLASSE_STYLE: Record<string, string> = {
  Rechtssubject: "bg-[#d8eaf7] text-ink border-[#a8b6c0]",
  Rechtsobject: "bg-[#b2c3e3] text-ink border-[#8a98b1]",
  Rechtsbetrekking: "bg-[#90a2d0] text-ink border-[#707ea2]",
  Rechtsfeit: "bg-[#bad8f1] text-ink border-[#91a8bb]",
  Voorwaarde: "bg-[#b7d8cd] text-ink border-[#8ea89f]",
  Afleidingsregel: "bg-[#d47479] text-ink border-[#a55a5e]",
  "Variabele en variabelewaarde": "bg-[#f5dc5e] text-ink border-[#bfab49]",
  "Parameter en parameterwaarde": "bg-[#e6b8bb] text-ink border-[#b38f91]",
  Operator: "bg-[#d7e8e2] text-ink border-[#a7b4b0]",
  Tijdsaanduiding: "bg-[#cbb8d6] text-ink border-[#9e8fa6]",
  Plaatsaanduiding: "bg-[#e6d3e5] text-ink border-[#b3a4b2]",
  "Delegatiebevoegdheid en delegatie-invulling": "bg-[#b0b1b2] text-ink border-[#898a8a]",
  Brondefinitie: "bg-[#edefef] text-ink border-[#b8baba]",
};

const NEUTRAAL = "bg-surface text-muted border-line";

export function jasStyle(klasse: string): string {
  return KLASSE_STYLE[klasse?.trim()] ?? NEUTRAAL;
}

export function isBekendeKlasse(klasse: string): boolean {
  return klasse?.trim() in KLASSE_STYLE;
}

/** Sorteersleutel voor presentatie: index in de canonieke wa-table-volgorde;
 *  onbekende klassen achteraan. Gebruik met een stabiele sort. */
export function jasVolgorde(klasse: string): number {
  const i = (JAS_KLASSEN as readonly string[]).indexOf(klasse?.trim());
  return i === -1 ? JAS_KLASSEN.length : i;
}
