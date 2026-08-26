import { describe, expect, it } from "vitest";
import { vereistAkkoord } from "./disclaimer";

describe("vereistAkkoord", () => {
  it("gate't de gewone pagina's", () => {
    expect(vereistAkkoord("/")).toBe(true);
  });

  it("gate't ook een deeplink naar een project", () => {
    expect(vereistAkkoord("/projecten/bwbr1-art9")).toBe(true);
  });

  it("laat de BFF-routes met rust (anders breken de SSE-streams)", () => {
    expect(vereistAkkoord("/api/projects/events")).toBe(false);
  });

  it("laat de disclaimer zelf met rust (anders een redirect-lus)", () => {
    expect(vereistAkkoord("/disclaimer")).toBe(false);
  });
});
