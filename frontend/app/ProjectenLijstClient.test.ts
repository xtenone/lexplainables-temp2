// De datumcel rendert zowel server-side (container: UTC) als in de browser (analist: NL). Deze
// tests borgen dat beide dezelfde tekst opleveren — anders krijg je een hydration-mismatch én een
// tijd die twee uur afwijkt van wat de analist verwacht.

import { afterEach, describe, expect, it } from "vitest";
import { formatDatum } from "./ProjectenLijstClient";

const OORSPRONKELIJKE_TZ = process.env.TZ;

afterEach(() => {
  process.env.TZ = OORSPRONKELIJKE_TZ;
});

describe("formatDatum", () => {
  it("geeft dezelfde tekst ongeacht de tijdzone van de omgeving", () => {
    const iso = "2026-07-30T12:00:00Z";
    process.env.TZ = "UTC";
    const alsUtc = formatDatum(iso);
    process.env.TZ = "America/New_York";
    const alsNewYork = formatDatum(iso);
    expect(alsNewYork).toBe(alsUtc);
  });

  it("toont de Nederlandse zomertijd (UTC+2), niet de UTC-tijd", () => {
    // 12:00 UTC op 30 juli = 14:00 in Europe/Amsterdam (CEST).
    expect(formatDatum("2026-07-30T12:00:00Z")).toContain("14:00");
  });

  it("toont de Nederlandse wintertijd (UTC+1)", () => {
    // 12:00 UTC op 30 januari = 13:00 in Europe/Amsterdam (CET).
    expect(formatDatum("2026-01-30T12:00:00Z")).toContain("13:00");
  });

  it("geeft een streepje bij een lege waarde", () => {
    expect(formatDatum("")).toBe("—");
  });

  it("laat een onparseerbare waarde ongemoeid terugkomen", () => {
    expect(formatDatum("geen-datum")).toBe("geen-datum");
  });
});
