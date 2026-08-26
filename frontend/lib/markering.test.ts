import { describe, expect, it } from "vitest";
import { markeerPassages, splitsOpPassages, type HastKnoop } from "./markering";

const zin = "De ontvanger zegt: “Hoofdelijk aansprakelijk is de bestuurder.” Zo staat het.";

describe("splitsOpPassages", () => {
  it("laat tekst zonder passages heel", () => {
    expect(splitsOpPassages(zin, [])).toEqual([{ tekst: zin, gemarkeerd: false }]);
  });

  it("knipt één passage eruit en markeert alleen die", () => {
    const uit = splitsOpPassages(zin, ["Hoofdelijk aansprakelijk is de bestuurder."]);
    expect(uit.map((s) => s.gemarkeerd)).toEqual([false, true, false]);
    expect(uit[1].tekst).toBe("Hoofdelijk aansprakelijk is de bestuurder.");
    // Niets mag verdwijnen: de stukken samen zijn weer de oorspronkelijke tekst.
    expect(uit.map((s) => s.tekst).join("")).toBe(zin);
  });

  it("markeert elk voorkomen, niet alleen het eerste", () => {
    const uit = splitsOpPassages("a X b X c", ["X"]);
    expect(uit.filter((s) => s.gemarkeerd)).toHaveLength(2);
    expect(uit.map((s) => s.tekst).join("")).toBe("a X b X c");
  });

  it("laat de langste passage winnen", () => {
    // Anders knipt "aansprakelijk" het langere citaat doormidden en staat er half gemarkeerde soep.
    const uit = splitsOpPassages(zin, ["aansprakelijk", "Hoofdelijk aansprakelijk is de bestuurder."]);
    expect(uit.filter((s) => s.gemarkeerd).map((s) => s.tekst)).toEqual([
      "Hoofdelijk aansprakelijk is de bestuurder.",
    ]);
  });

  it("markeert niets als de weergave afwijkt van wat de controle vergeleek", () => {
    // De controle normaliseert witruimte, de weergave niet. Liever niets aanwijzen dan het
    // verkeerde stuk; het blok onder het antwoord noemt de passage dan nog steeds.
    const uit = splitsOpPassages(zin, ["Hoofdelijk  aansprakelijk"]);
    expect(uit).toEqual([{ tekst: zin, gemarkeerd: false }]);
  });

  it("negeert lege passages en dubbelen", () => {
    const uit = splitsOpPassages("a X b", ["", "  ", "X", "X"]);
    expect(uit.filter((s) => s.gemarkeerd)).toHaveLength(1);
  });

  it("geeft niets terug bij lege tekst", () => {
    expect(splitsOpPassages("", ["X"])).toEqual([]);
  });
});

// --- de rehype-plugin: een boomtransformatie, dus zonder DOM te testen -------------------------

function tekst(v: string): HastKnoop {
  return { type: "text", value: v };
}
function el(tagName: string, ...children: HastKnoop[]): HastKnoop {
  return { type: "element", tagName, children };
}
/** Alleen de gemarkeerde stukken, in volgorde. */
function gemarkeerd(knoop: HastKnoop): string[] {
  if (knoop.tagName === "mark") return [(knoop.children ?? []).map((k) => k.value ?? "").join("")];
  return (knoop.children ?? []).flatMap(gemarkeerd);
}
/** Alle zichtbare tekst, om te bewijzen dat er niets verdwijnt of bij komt. */
function alleTekst(knoop: HastKnoop): string {
  if (knoop.type === "text") return knoop.value ?? "";
  return (knoop.children ?? []).map(alleTekst).join("");
}

describe("markeerPassages", () => {
  it("wikkelt een afgekeurd citaat in een mark, diep in de boom", () => {
    const boom = el("root", el("p", tekst("Zie: “Hoofdelijk aansprakelijk.” Aldus.")));
    markeerPassages(["Hoofdelijk aansprakelijk."])()(boom);
    expect(gemarkeerd(boom)).toEqual(["Hoofdelijk aansprakelijk."]);
    expect(alleTekst(boom)).toBe("Zie: “Hoofdelijk aansprakelijk.” Aldus.");
  });

  it("laat de tekst ongemoeid als er niets af te keuren valt", () => {
    const boom = el("root", el("p", tekst("Gewoon een antwoord.")));
    markeerPassages(["iets anders"])()(boom);
    expect(gemarkeerd(boom)).toEqual([]);
    expect(alleTekst(boom)).toBe("Gewoon een antwoord.");
  });

  it("slaat code over — een treffer daarin is toeval", () => {
    const boom = el("root", el("pre", el("code", tekst("select X from Y"))));
    markeerPassages(["select X"])()(boom);
    expect(gemarkeerd(boom)).toEqual([]);
  });

  it("markeert door verschillende elementen heen", () => {
    const boom = el(
      "root",
      el("p", tekst("Eerst “A B C”.")),
      el("li", tekst("En ook “A B C” hier.")),
    );
    markeerPassages(["A B C"])()(boom);
    expect(gemarkeerd(boom)).toEqual(["A B C", "A B C"]);
  });

  it("raakt opmaak binnen een citaat niet kwijt", () => {
    // Vet binnen een citaat is precies wat de controle afkeurt; de tekstknopen eromheen worden dan
    // apart gemarkeerd. Het mag in elk geval geen tekst opeten.
    const boom = el("root", el("p", tekst("“wordt "), el("strong", tekst("vermoed")), tekst(" dat”")));
    markeerPassages(["wordt "])()(boom);
    expect(alleTekst(boom)).toBe("“wordt vermoed dat”");
  });
});
