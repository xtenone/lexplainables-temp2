import { describe, expect, it } from "vitest";
import { buildStartRequest, parseBegrippenlijst, projectSchema } from "./projectForm";

describe("projectSchema", () => {
  it("eist minstens één bron met een niet-leeg artikel", () => {
    const geen = projectSchema.safeParse({ bronnen: [], review: true });
    expect(geen.success).toBe(false);
    const leeg = projectSchema.safeParse({ bronnen: [{ artikel: "" }], review: true });
    expect(leeg.success).toBe(false);
    const spaties = projectSchema.safeParse({ bronnen: [{ artikel: "   " }], review: true });
    expect(spaties.success).toBe(false); // trim → leeg
  });

  it("trimt waarden en accepteert een geldig artikel", () => {
    const r = projectSchema.safeParse({ bronnen: [{ artikel: "  9  " }], review: true });
    expect(r.success).toBe(true);
    if (r.success) expect(r.data.bronnen[0].artikel).toBe("9");
  });

  it("weigert te lange velden", () => {
    expect(
      projectSchema.safeParse({ bronnen: [{ artikel: "1", bwbId: "x".repeat(65) }], review: true }).success,
    ).toBe(false);
    expect(projectSchema.safeParse({ bronnen: [{ artikel: "x".repeat(33) }], review: true }).success).toBe(false);
  });
});

describe("buildStartRequest", () => {
  it("laat lege optionele velden weg, behoudt bronnen + review", () => {
    const body = buildStartRequest({ bronnen: [{ artikel: "9" }], review: true });
    expect(body).toEqual({ bronnen: [{ artikel: "9" }], review: true });
    expect("naam" in body).toBe(false);
    expect("model_profile" in body).toBe(false);
  });

  it("neemt een geparseerde begrippenlijst mee en laat een lege weg", () => {
    const zonder = buildStartRequest({ bronnen: [{ artikel: "9" }], review: true, begrippenlijst: [] });
    expect("begrippenlijst" in zonder).toBe(false);
    const met = buildStartRequest({
      bronnen: [{ artikel: "9" }],
      review: true,
      begrippenlijst: [{ naam: "belastingplichtige" }],
    });
    expect(met.begrippenlijst).toEqual([{ naam: "belastingplichtige" }]);
  });

  it("neemt meerdere bronnen en optionele velden mee", () => {
    const body = buildStartRequest({
      bronnen: [
        { artikel: "43", bwbId: "BWBR0018450", lid: "2" },
        { artikel: "5.6", bwbId: "BWBR0018715" },
      ],
      review: false,
      naam: "Iab Zvw",
      omschrijving: "context",
      analysefocus: "vraag",
      model_profile: "azure-sonnet",
    });
    expect(body).toEqual({
      bronnen: [
        { artikel: "43", bwbId: "BWBR0018450", lid: "2" },
        { artikel: "5.6", bwbId: "BWBR0018715" },
      ],
      review: false,
      naam: "Iab Zvw",
      omschrijving: "context",
      analysefocus: "vraag",
      model_profile: "azure-sonnet",
    });
  });
});

describe("parseBegrippenlijst", () => {
  it("parseert canonieke JSON ({begrippen: [...]}) en een kale array", () => {
    const canoniek = parseBegrippenlijst(
      '{"begrippen": [{"naam": "belastingplichtige", "definitie": "d", "synoniemen": ["plichtige"]}]}',
    );
    expect(canoniek.fouten).toEqual([]);
    expect(canoniek.begrippen).toEqual([
      { naam: "belastingplichtige", definitie: "d", synoniemen: ["plichtige"] },
    ]);
    const kaal = parseBegrippenlijst('[{"naam": "bijdrage-inkomen"}, "premie"]');
    expect(kaal.begrippen).toEqual([{ naam: "bijdrage-inkomen" }, { naam: "premie" }]);
  });

  it("meldt ongeldige JSON en ontbrekende namen als fout", () => {
    expect(parseBegrippenlijst("{kapot").fouten.length).toBeGreaterThan(0);
    const r = parseBegrippenlijst('{"begrippen": [{"definitie": "zonder naam"}]}');
    expect(r.begrippen).toEqual([]);
    expect(r.fouten[0]).toMatch(/naam/);
  });

  it("parseert CSV met kopregel (komma en puntkomma, synoniemen met |)", () => {
    const komma = parseBegrippenlijst(
      'naam,definitie,klasse,synoniemen\nbelastingplichtige,"degene, die",Rechtssubject,plichtige|subject',
    );
    expect(komma.fouten).toEqual([]);
    expect(komma.begrippen).toEqual([{
      naam: "belastingplichtige",
      definitie: "degene, die",
      klasse: "Rechtssubject",
      synoniemen: ["plichtige", "subject"],
    }]);
    const punt = parseBegrippenlijst("naam;definitie\npremie;maandelijkse afdracht");
    expect(punt.begrippen).toEqual([{ naam: "premie", definitie: "maandelijkse afdracht" }]);
  });

  it("parseert platte regels als `naam; definitie` of alleen naam", () => {
    const r = parseBegrippenlijst(
      "belastingplichtige; degene die aangifte moet doen\nbijdrage-inkomen\n",
    );
    expect(r.fouten).toEqual([]);
    expect(r.begrippen).toEqual([
      { naam: "belastingplichtige", definitie: "degene die aangifte moet doen" },
      { naam: "bijdrage-inkomen" },
    ]);
  });

  it("geeft leeg resultaat op lege invoer", () => {
    expect(parseBegrippenlijst("   \n ")).toEqual({ begrippen: [], fouten: [] });
  });

  it("dropt geen begrip als de eerste regel toevallig een kolomnaam is (geen valse CSV-header)", () => {
    // Één term per regel; regel 1 = "naam" mag NIET als kopregel worden opgevat (≥2 kolommen vereist).
    const r = parseBegrippenlijst("naam\npremie\ninkomen");
    expect(r.fouten).toEqual([]);
    expect(r.begrippen).toEqual([{ naam: "naam" }, { naam: "premie" }, { naam: "inkomen" }]);
  });
});
