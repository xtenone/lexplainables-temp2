import { describe, expect, it } from "vitest";
import type { JobState } from "./types";
import {
  STATE_LABEL,
  isDeletable,
  isReview,
  isRunning,
  isTerminal,
  reviewActiviteit,
} from "./states";

const ALLE_STATES: JobState[] = [
  "queued",
  "act2-runt",
  "wacht-op-review-act2",
  "act3-runt",
  "wacht-op-review-act3",
  "bouwt",
  "klaar",
  "fout",
  "rs-gegevens-runt",
  "wacht-op-review-rs-gegevens",
  "rs-regels-runt",
  "wacht-op-review-rs-regels",
  "rs-bouwt",
  "rs-klaar",
];

describe("state-classificatie", () => {
  it("merkt review-states als review (en niet als running/terminal)", () => {
    for (const s of ["wacht-op-review-act2", "wacht-op-review-act3"] as JobState[]) {
      expect(isReview(s)).toBe(true);
      expect(isRunning(s)).toBe(false);
      expect(isTerminal(s)).toBe(false);
    }
  });

  it("merkt lopende states als running", () => {
    for (const s of ["queued", "act2-runt", "act3-runt", "bouwt"] as JobState[]) {
      expect(isRunning(s)).toBe(true);
      expect(isTerminal(s)).toBe(false);
    }
  });

  it("merkt klaar/fout als terminal", () => {
    expect(isTerminal("klaar")).toBe(true);
    expect(isTerminal("fout")).toBe(true);
  });

  it("classificeert de RegelSpraak-vervolgstates", () => {
    for (const s of ["rs-gegevens-runt", "rs-regels-runt", "rs-bouwt"] as JobState[]) {
      expect(isRunning(s), s).toBe(true);
      expect(isTerminal(s), s).toBe(false);
    }
    for (const s of ["wacht-op-review-rs-gegevens", "wacht-op-review-rs-regels"] as JobState[]) {
      expect(isReview(s), s).toBe(true);
      expect(isRunning(s), s).toBe(false);
    }
    expect(isTerminal("rs-klaar")).toBe(true);
  });

  it("elke state is in precies één categorie", () => {
    for (const s of ALLE_STATES) {
      const n = [isReview(s), isRunning(s), isTerminal(s)].filter(Boolean).length;
      expect(n, s).toBe(1);
    }
  });

  it("spiegelt de upstream delete-regel (terminaal/review/queued wel, lopend niet)", () => {
    expect(isDeletable("queued")).toBe(true);
    expect(isDeletable("klaar")).toBe(true);
    expect(isDeletable("fout")).toBe(true);
    expect(isDeletable("rs-klaar")).toBe(true);
    expect(isDeletable("wacht-op-review-act3")).toBe(true);
    for (const s of ["act2-runt", "act3-runt", "bouwt", "rs-gegevens-runt",
                     "rs-regels-runt", "rs-bouwt"] as JobState[]) {
      expect(isDeletable(s), s).toBe(false);
    }
  });

  it("koppelt review-states aan hun activiteit", () => {
    expect(reviewActiviteit("wacht-op-review-act2")).toBe("2");
    expect(reviewActiviteit("wacht-op-review-act3")).toBe("3");
    expect(reviewActiviteit("wacht-op-review-rs-gegevens")).toBe("rs-gegevens");
    expect(reviewActiviteit("wacht-op-review-rs-regels")).toBe("rs-regels");
    expect(reviewActiviteit("queued")).toBeNull();
  });

  it("heeft een label voor elke state", () => {
    for (const s of ALLE_STATES) expect(STATE_LABEL[s]).toBeTruthy();
  });
});
