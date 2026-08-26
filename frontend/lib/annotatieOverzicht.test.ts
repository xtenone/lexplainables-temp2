import { describe, expect, it } from "vitest";

import {
  groepeerPerRegeling, isTeDoen, kleurstrip, sorteerTeDoen, vindplaatsLabel, weergaveUitParam, zoek,
} from "./annotatieOverzicht";
import { JAS_KLASSEN } from "./jas";
import type { DocumentSamenvatting } from "./types";

function doc(over: Partial<DocumentSamenvatting> = {}): DocumentSamenvatting {
  return {
    slug: "s1", bwbId: "BWBR1", artikel: "9", lid: "", citeertitel: "Invorderingswet 1990",
    werkgebied: "", status: "in_review", aantal_elementen: 3, te_beoordelen: 3,
    per_aandacht: {}, per_klasse: {}, laatste_model: "", updated: "2026-08-01T10:00:00Z",
    ...over,
  };
}

describe("te doen", () => {
  it("telt alleen wat de jurist niet heeft afgerond", () => {
    expect(isTeDoen(doc({ te_beoordelen: 2 }))).toBe(true);
    expect(isTeDoen(doc({ te_beoordelen: 0 }))).toBe(false);
    // Afgerond mét open elementen is een bewuste keuze, geen restpost.
    expect(isTeDoen(doc({ status: "geaccordeerd", te_beoordelen: 5 }))).toBe(false);
  });

  it("zet rood boven geel, en daarna wat het langst stil ligt", () => {
    const geel = doc({ slug: "geel", per_aandacht: { geel: 4 } });
    const rood = doc({ slug: "rood", per_aandacht: { rood: 1 } });
    const oud = doc({ slug: "oud", updated: "2026-01-01T10:00:00Z" });
    const nieuw = doc({ slug: "nieuw", updated: "2026-08-18T10:00:00Z" });

    expect(sorteerTeDoen([nieuw, geel, oud, rood]).map((d) => d.slug))
      .toEqual(["rood", "geel", "oud", "nieuw"]);
  });

  it("laat de invoer ongemoeid", () => {
    const lijst = [doc({ slug: "a" }), doc({ slug: "b", per_aandacht: { rood: 1 } })];
    sorteerTeDoen(lijst);
    expect(lijst.map((d) => d.slug)).toEqual(["a", "b"]);
  });
});

describe("groeperen per regeling", () => {
  it("groepeert op bwbId en sorteert artikelen numeriek", () => {
    const groepen = groepeerPerRegeling([
      doc({ slug: "a", bwbId: "BWBR1", artikel: "10" }),
      doc({ slug: "b", bwbId: "BWBR1", artikel: "2" }),
      doc({ slug: "c", bwbId: "BWBR2", citeertitel: "Awb" }),
    ]);

    expect(groepen.map((g) => g.naam)).toEqual(["Awb", "Invorderingswet 1990"]);
    // '10' na '2': lexicaal sorteren zou de volgorde omdraaien.
    expect(groepen[1].documenten.map((d) => d.artikel)).toEqual(["2", "10"]);
  });

  it("valt terug op het bwbId als er geen naam is", () => {
    expect(groepeerPerRegeling([doc({ citeertitel: "" })])[0].naam).toBe("BWBR1");
  });

  it("sorteert leden numeriek binnen hetzelfde artikel", () => {
    const groep = groepeerPerRegeling([
      doc({ slug: "a", artikel: "9", lid: "10" }),
      doc({ slug: "b", artikel: "9", lid: "2" }),
    ])[0];
    expect(groep.documenten.map((d) => d.lid)).toEqual(["2", "10"]);
  });
});

describe("zoeken", () => {
  const lijst = [
    doc({ slug: "iw", citeertitel: "Invorderingswet 1990", artikel: "9" }),
    doc({ slug: "zvw", citeertitel: "Zorgverzekeringswet", bwbId: "BWBR2", artikel: "43", lid: "2" }),
  ];

  it("matcht woord voor woord, ongeacht volgorde", () => {
    expect(zoek(lijst, "zorgverzekering 43").map((d) => d.slug)).toEqual(["zvw"]);
    expect(zoek(lijst, "43 zorg").map((d) => d.slug)).toEqual(["zvw"]);
  });

  it("geeft alles terug bij een lege term", () => {
    expect(zoek(lijst, "   ")).toHaveLength(2);
  });

  it("vindt op bwbId en op de vindplaats", () => {
    expect(zoek(lijst, "BWBR2").map((d) => d.slug)).toEqual(["zvw"]);
    expect(zoek(lijst, "lid 2").map((d) => d.slug)).toEqual(["zvw"]);
  });
});

describe("kleurstrip", () => {
  it("volgt de canonieke JAS-volgorde, niet de invoervolgorde", () => {
    const strip = kleurstrip({ Voorwaarde: 2, Rechtssubject: 5 }, JAS_KLASSEN);
    expect(strip).toEqual([
      { klasse: "Rechtssubject", aantal: 5 },
      { klasse: "Voorwaarde", aantal: 2 },
    ]);
  });

  it("laat onbekende klassen niet verdwijnen — de strip mag niet liegen", () => {
    const strip = kleurstrip({ Rechtssubject: 1, Verzonnen: 3 }, JAS_KLASSEN);
    expect(strip.map((s) => s.klasse)).toEqual(["Rechtssubject", "Verzonnen"]);
  });

  it("slaat nullen over", () => {
    expect(kleurstrip({ Rechtssubject: 0 }, JAS_KLASSEN)).toEqual([]);
  });
});

describe("weergave", () => {
  it("valt terug op de werkvoorraad", () => {
    expect(weergaveUitParam("alles")).toBe("alles");
    expect(weergaveUitParam(null)).toBe("te-doen");
    expect(weergaveUitParam("onzin")).toBe("te-doen");
  });
});

describe("vindplaats", () => {
  it("noemt het lid alleen als het er is", () => {
    expect(vindplaatsLabel(doc())).toBe("art. 9");
    expect(vindplaatsLabel(doc({ lid: "2" }))).toBe("art. 9 lid 2");
  });
});
