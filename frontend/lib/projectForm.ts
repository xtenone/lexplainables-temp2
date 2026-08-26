// Pure validatie- en body-bouwlogica voor het analyseformulier, los van de React-component
// zodat ze direct te unit-testen is. De UI (components/ProjectForm.tsx) gebruikt deze helpers.

import { z } from "zod";
import type { BegripInvoer, BronInput, StartRequest } from "./types";

// Eén bron-rij in het werkgebied (wet + artikel + lid).
export const bronSchema = z.object({
  bwbId: z.string().trim().max(64).optional(),
  artikel: z.string().trim().min(1, "Artikel is verplicht").max(32),
  lid: z.string().trim().max(16).optional(),
});

export type BronFormValue = z.infer<typeof bronSchema>;

// Caps spiegelen de API (BegripInvoer in contracts.py): max 300 items, naam ≤200, definitie ≤2000.
export const begripInvoerSchema = z.object({
  id: z.string().trim().max(32).optional(),
  naam: z.string().trim().min(1, "Naam is verplicht").max(200),
  synoniemen: z.array(z.string().trim().max(200)).max(20).optional(),
  definitie: z.string().trim().max(2000).optional(),
  klasse: z.string().trim().max(64).optional(),
  bron: z.string().trim().max(200).optional(),
  toelichting: z.string().trim().max(1000).optional(),
});

export const projectSchema = z.object({
  bronnen: z.array(bronSchema).min(1, "Voeg minstens één bron toe"),
  naam: z.string().trim().max(200).optional(),
  omschrijving: z.string().trim().max(2000).optional(),
  analysefocus: z.string().trim().max(2000).optional(),
  begrippenlijst: z.array(begripInvoerSchema).max(300, "Maximaal 300 begrippen").optional(),
  review: z.boolean(),
  model_profile: z.string().trim().max(64).optional(),
});

export type ProjectFormValues = z.infer<typeof projectSchema>;

/** Eén lege bron-rij voor het formulier. */
export function legeBron(): BronFormValue {
  return { bwbId: "", artikel: "", lid: "" };
}

/** Bouw de API-body: laat lege optionele velden weg zodat de API z'n defaults gebruikt. */
export function buildStartRequest(d: ProjectFormValues): StartRequest {
  const bronnen: BronInput[] = d.bronnen.map((b) => {
    const out: BronInput = { artikel: b.artikel };
    if (b.bwbId) out.bwbId = b.bwbId;
    if (b.lid) out.lid = b.lid;
    return out;
  });
  const body: StartRequest = { bronnen, review: d.review };
  if (d.naam) body.naam = d.naam;
  if (d.omschrijving) body.omschrijving = d.omschrijving;
  if (d.analysefocus) body.analysefocus = d.analysefocus;
  if (d.begrippenlijst?.length) body.begrippenlijst = d.begrippenlijst;
  if (d.model_profile) body.model_profile = d.model_profile;
  return body;
}

export interface ParseResultaat {
  begrippen: BegripInvoer[];
  fouten: string[];
}

/** Splits één CSV-regel (komma of puntkomma), met steun voor "quoted" velden. */
function splitsCsvRegel(regel: string, scheider: string): string[] {
  const velden: string[] = [];
  let huidig = "";
  let inQuotes = false;
  for (let i = 0; i < regel.length; i++) {
    const c = regel[i];
    if (c === '"') {
      if (inQuotes && regel[i + 1] === '"') {
        huidig += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (c === scheider && !inQuotes) {
      velden.push(huidig);
      huidig = "";
    } else {
      huidig += c;
    }
  }
  velden.push(huidig);
  return velden.map((v) => v.trim());
}

const CSV_KOLOMMEN = new Set(["id", "naam", "synoniemen", "definitie", "klasse", "bron", "toelichting"]);

function naarBegrip(obj: Record<string, unknown>, regelNr: number, fouten: string[]): BegripInvoer | null {
  const naam = String(obj.naam ?? "").trim();
  if (!naam) {
    fouten.push(`Regel ${regelNr}: 'naam' ontbreekt of is leeg.`);
    return null;
  }
  const b: BegripInvoer = { naam };
  if (obj.id) b.id = String(obj.id).trim();
  if (obj.definitie) b.definitie = String(obj.definitie).trim();
  if (obj.klasse) b.klasse = String(obj.klasse).trim();
  if (obj.bron) b.bron = String(obj.bron).trim();
  if (obj.toelichting) b.toelichting = String(obj.toelichting).trim();
  if (obj.synoniemen) {
    const syn = Array.isArray(obj.synoniemen)
      ? obj.synoniemen.map((s) => String(s).trim())
      : String(obj.synoniemen).split("|").map((s) => s.trim());
    const gevuld = syn.filter(Boolean);
    if (gevuld.length) b.synoniemen = gevuld;
  }
  return b;
}

/**
 * Parseer een geplakte/geüploade bestaande begrippenlijst. Drie vormen:
 *  1. JSON — canoniek `{begrippen: [...]}` of een kale array;
 *  2. CSV met kopregel (`naam` verplicht; komma of puntkomma; synoniemen gescheiden met `|`);
 *  3. platte regels — `naam` of `naam; definitie` per regel.
 * Puur en client-side; de API valideert de caps opnieuw (Pydantic).
 */
export function parseBegrippenlijst(tekst: string): ParseResultaat {
  const fouten: string[] = [];
  const schoon = tekst.trim();
  if (!schoon) return { begrippen: [], fouten };

  // 1. JSON (canoniek of kale array).
  if (schoon.startsWith("{") || schoon.startsWith("[")) {
    try {
      const data = JSON.parse(schoon) as unknown;
      const lijst = Array.isArray(data)
        ? data
        : ((data as { begrippen?: unknown[] })?.begrippen ?? null);
      if (!Array.isArray(lijst)) {
        return { begrippen: [], fouten: ["JSON herkend, maar geen 'begrippen'-array gevonden."] };
      }
      const begrippen: BegripInvoer[] = [];
      lijst.forEach((item, i) => {
        if (typeof item === "string") {
          if (item.trim()) begrippen.push({ naam: item.trim() });
          return;
        }
        const b = naarBegrip((item ?? {}) as Record<string, unknown>, i + 1, fouten);
        if (b) begrippen.push(b);
      });
      return { begrippen, fouten };
    } catch {
      return { begrippen: [], fouten: ["Ongeldige JSON — controleer de syntaxis."] };
    }
  }

  const regels = schoon.split(/\r?\n/).map((r) => r.trim()).filter(Boolean);

  // 2. CSV met kopregel: eerste regel is een écht meerkoloms-kopje (≥2 kolommen) met een 'naam'-kolom.
  // De ≥2-eis voorkomt dat een platte één-begrip-per-regel-lijst waarvan de eerste regel toevallig
  // exact "naam" (of een andere kolomnaam) is, als header wordt opgevat en het eerste begrip stil dropt.
  const scheider = regels[0].includes(";") && !regels[0].includes(",") ? ";" : ",";
  const kop = splitsCsvRegel(regels[0], scheider).map((k) => k.toLowerCase());
  if (kop.length >= 2 && kop.includes("naam") && kop.every((k) => !k || CSV_KOLOMMEN.has(k))) {
    const begrippen: BegripInvoer[] = [];
    for (let i = 1; i < regels.length; i++) {
      const velden = splitsCsvRegel(regels[i], scheider);
      const obj: Record<string, unknown> = {};
      kop.forEach((k, j) => {
        if (k) obj[k] = velden[j] ?? "";
      });
      const b = naarBegrip(obj, i + 1, fouten);
      if (b) begrippen.push(b);
    }
    return { begrippen, fouten };
  }

  // 3. Platte regels: `naam` of `naam; definitie`.
  const begrippen: BegripInvoer[] = [];
  regels.forEach((regel, i) => {
    const [naam, ...rest] = regel.split(";");
    const b = naarBegrip({ naam, definitie: rest.join(";") }, i + 1, fouten);
    if (b) begrippen.push(b);
  });
  return { begrippen, fouten };
}
