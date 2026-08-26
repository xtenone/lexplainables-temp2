import { describe, expect, it } from "vitest";
import { bestaatArtikel, filterArtikelen, isBwbId, telTreffers } from "./artikelFilter";
import type { ArtikelChoice } from "./types";

const items: ArtikelChoice[] = [
  { artikel: "1", pad: "Hoofdstuk 1" },
  { artikel: "9", pad: "Hoofdstuk 2" },
  { artikel: "9a", pad: "Hoofdstuk 2" },
  { artikel: "9b", pad: "Hoofdstuk 2" },
  { artikel: "19", pad: "Hoofdstuk 3" },
  { artikel: "96", pad: "Hoofdstuk 9" },
];

describe("filterArtikelen", () => {
  it("rangschikt exact → begint-met → bevat, in documentvolgorde per groep", () => {
    expect(filterArtikelen(items, "9").map((i) => i.artikel)).toEqual(["9", "9a", "9b", "96", "19"]);
  });

  it("is case-insensitief en trimt de query", () => {
    expect(filterArtikelen(items, " 9A ").map((i) => i.artikel)).toEqual(["9a"]);
  });

  it("geeft bij lege query de eerste max items in documentvolgorde", () => {
    expect(filterArtikelen(items, "", 3).map((i) => i.artikel)).toEqual(["1", "9", "9a"]);
  });

  it("respecteert de cap ook bij een gevulde query", () => {
    expect(filterArtikelen(items, "9", 2).map((i) => i.artikel)).toEqual(["9", "9a"]);
  });

  it("geeft niets bij geen treffers", () => {
    expect(filterArtikelen(items, "42")).toEqual([]);
  });
});

describe("telTreffers", () => {
  it("telt zonder cap", () => {
    expect(telTreffers(items, "9")).toBe(5);
    expect(telTreffers(items, "")).toBe(6);
  });
});

describe("bestaatArtikel", () => {
  it("matcht exact en case-insensitief", () => {
    expect(bestaatArtikel(items, "9a")).toBe(true);
    expect(bestaatArtikel(items, "9A ")).toBe(true);
    expect(bestaatArtikel(items, "9c")).toBe(false);
    expect(bestaatArtikel(items, "")).toBe(false);
  });
});

describe("isBwbId", () => {
  it("herkent BWBR/BWBV/BWBW-ids, met trim en case-insensitief", () => {
    expect(isBwbId("BWBR0004770")).toBe(true);
    expect(isBwbId(" bwbv0001000 ")).toBe(true);
    expect(isBwbId("BWBR")).toBe(false);
    expect(isBwbId("Zorgverzekeringswet")).toBe(false);
    expect(isBwbId("")).toBe(false);
  });
});
