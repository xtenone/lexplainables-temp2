import { describe, expect, it } from "vitest";
import { vereistAkkoord } from "./disclaimer";

describe("vereistAkkoord", () => {
  it("gate't de gewone pagina's", () => {
    expect(vereistAkkoord("/")).toBe(true);
  });

  it("gate't ook een deeplink naar de werkruimte", () => {
    expect(vereistAkkoord("/workbench")).toBe(true);
  });

  it("laat de BFF-routes met rust (anders breekt de SSE-stream)", () => {
    expect(vereistAkkoord("/api/annotatie/run/r1/events")).toBe(false);
  });

  it("laat de disclaimer zelf met rust (anders een redirect-lus)", () => {
    expect(vereistAkkoord("/disclaimer")).toBe(false);
  });
});
