// Het fijnmazige fase-vocabulaire BINNEN een runt/bouwt-state — de "functieniveau"-laag van het
// dashboard. Spiegelt 1-op-1 orchestrator.py:_genereer()/_bouw_rapport() in de API; verzin hier
// geen fasen bij (brongetrouw, ook in de UI). De macro-states blijven in lib/states.ts.

import type { JobState } from "./types";

export const FASE_LABEL: Record<string, string> = {
  "wettekst-ophalen": "Wettekst ophalen",
  "verwijzingen-inventariseren": "Verwijzingen inventariseren",
  "verwijzingen-volgen": "Verwijzingen volgen",
  "llm-generatie": "LLM-generatie",
  "auto-correctie": "Auto-correctie",
  "brongetrouwheid-check": "Brongetrouwheid-check",
  "schema-check": "Schema-check",
  "analyse-wegschrijven": "Analyse wegschrijven",
  reviewlog: "Reviewlog",
  aandachtspunten: "Aandachtspunten",
  "rapport-wegschrijven": "Rapport wegschrijven",
  "regelspraak-gegevens-generatie": "GegevensSpraak genereren",
  "regelspraak-regels-generatie": "RegelSpraak-regels genereren",
  "regelspraak-bouwt": "RegelSpraak-model samenstellen",
};

// Activiteit 2 is twee-fase (incl. verwijzingen); activiteit 3 slaat de verwijzing-stappen over.
const ACT2_FASEN = [
  "wettekst-ophalen",
  "verwijzingen-inventariseren",
  "verwijzingen-volgen",
  "llm-generatie",
  "auto-correctie",
  "brongetrouwheid-check",
  "schema-check",
  "analyse-wegschrijven",
];
const ACT3_FASEN = ACT2_FASEN.filter(
  (f) => f !== "verwijzingen-inventariseren" && f !== "verwijzingen-volgen",
);
const BOUWT_FASEN = ["reviewlog", "aandachtspunten", "rapport-wegschrijven"];
// RegelSpraak-stappen: generatie → brongetrouwheid/schema-check → wegschrijven (deelt de generieke fasen).
const RS_GEGEVENS_FASEN = [
  "regelspraak-gegevens-generatie", "auto-correctie",
  "brongetrouwheid-check", "schema-check", "analyse-wegschrijven",
];
const RS_REGELS_FASEN = [
  "regelspraak-regels-generatie", "auto-correctie",
  "brongetrouwheid-check", "schema-check", "analyse-wegschrijven",
];

const FASEN_PER_MACRO: Partial<Record<JobState, string[]>> = {
  "act2-runt": ACT2_FASEN,
  "act3-runt": ACT3_FASEN,
  bouwt: BOUWT_FASEN,
  "rs-gegevens-runt": RS_GEGEVENS_FASEN,
  "rs-regels-runt": RS_REGELS_FASEN,
  "rs-bouwt": ["regelspraak-bouwt"],
};

/** De geordende functiefasen voor een macro-state; leeg buiten een runt/bouwt-state. */
export function fasenVoor(state: JobState): string[] {
  return FASEN_PER_MACRO[state] ?? [];
}

export function faseLabel(fase: string | null): string {
  return fase ? FASE_LABEL[fase] ?? fase : "";
}
