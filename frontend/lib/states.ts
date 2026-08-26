import type { Activiteit, JobState } from "./types";

export const STATE_LABEL: Record<JobState, string> = {
  queued: "In wachtrij",
  "act2-runt": "Activiteit 2 — markeren",
  "wacht-op-review-act2": "Wacht op review (act. 2)",
  "act3-runt": "Activiteit 3 — begrippen",
  "wacht-op-review-act3": "Wacht op review (act. 3)",
  bouwt: "Rapport samenstellen",
  klaar: "Klaar",
  fout: "Fout",
  "rs-gegevens-runt": "RegelSpraak — GegevensSpraak",
  "wacht-op-review-rs-gegevens": "Wacht op review (GegevensSpraak)",
  "rs-regels-runt": "RegelSpraak — regels",
  "wacht-op-review-rs-regels": "Wacht op review (regels)",
  "rs-bouwt": "RegelSpraak-model samenstellen",
  "rs-klaar": "RegelSpraak klaar",
};

// Badge-stijl per state (Tailwind), afgestemd op de Rijkshuisstijl: lopend = lintblauw,
// review = aandacht-oranje, klaar = succes-groen, fout = rood. Tekst voldoet aan ≥ 4,5:1.
export const STATE_STYLE: Record<JobState, string> = {
  queued: "bg-surface text-muted border-line",
  "act2-runt": "bg-[#e7eef5] text-[#154273] border-[#bcd2e6]",
  "wacht-op-review-act2": "bg-[#fbefe2] text-[#8e4600] border-[#e7c9a8]",
  "act3-runt": "bg-[#e7eef5] text-[#154273] border-[#bcd2e6]",
  "wacht-op-review-act3": "bg-[#fbefe2] text-[#8e4600] border-[#e7c9a8]",
  bouwt: "bg-[#ece9f2] text-[#473a5e] border-[#d2c8dd]",
  klaar: "bg-[#e6f0e0] text-[#2c6608] border-[#bcd9a8]",
  fout: "bg-[#fbe7e5] text-[#b01b10] border-[#f0bcb6]",
  "rs-gegevens-runt": "bg-[#e7eef5] text-[#154273] border-[#bcd2e6]",
  "wacht-op-review-rs-gegevens": "bg-[#fbefe2] text-[#8e4600] border-[#e7c9a8]",
  "rs-regels-runt": "bg-[#e7eef5] text-[#154273] border-[#bcd2e6]",
  "wacht-op-review-rs-regels": "bg-[#fbefe2] text-[#8e4600] border-[#e7c9a8]",
  "rs-bouwt": "bg-[#ece9f2] text-[#473a5e] border-[#d2c8dd]",
  "rs-klaar": "bg-[#e6f0e0] text-[#2c6608] border-[#bcd9a8]",
};

export const RUNNING_STATES: JobState[] = [
  "queued", "act2-runt", "act3-runt", "bouwt",
  "rs-gegevens-runt", "rs-regels-runt", "rs-bouwt",
];
export const REVIEW_STATES: JobState[] = [
  "wacht-op-review-act2", "wacht-op-review-act3",
  "wacht-op-review-rs-gegevens", "wacht-op-review-rs-regels",
];
export const TERMINAL_STATES: JobState[] = ["klaar", "fout", "rs-klaar"];

export function isReview(state: JobState): boolean {
  return REVIEW_STATES.includes(state);
}
export function isRunning(state: JobState): boolean {
  return RUNNING_STATES.includes(state);
}
export function isTerminal(state: JobState): boolean {
  return TERMINAL_STATES.includes(state);
}

/** Spiegelt de upstream delete-regel (DELETE /v1/projects/{id}): verwijderen mag vanuit een
 *  eindstaat, een review-pauze of `queued` (verweesde job); lopende states geven 409. */
export function isDeletable(state: JobState): boolean {
  return isTerminal(state) || isReview(state) || state === "queued";
}

/** Macro-statusgroepen voor tellers en filters (gelijk aan de dashboard-indeling). */
export type StatusBucket = "lopend" | "review" | "klaar" | "fout";

export function statusBucket(state: JobState, error?: unknown): StatusBucket {
  if (state === "fout" || error) return "fout";
  if (isReview(state)) return "review";
  if (state === "klaar" || state === "rs-klaar") return "klaar";
  return "lopend";
}

/** Welke activiteit hoort bij een review-state? */
export function reviewActiviteit(state: JobState): Activiteit | null {
  if (state === "wacht-op-review-act2") return "2";
  if (state === "wacht-op-review-act3") return "3";
  if (state === "wacht-op-review-rs-gegevens") return "rs-gegevens";
  if (state === "wacht-op-review-rs-regels") return "rs-regels";
  return null;
}
