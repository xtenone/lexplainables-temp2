import { describe, expect, it } from "vitest";

import { segmenteer } from "./DocumentPaneel";

const BRON = "De ontvanger kan uitstel van betaling verlenen aan de belastingschuldige.";

describe("segmenteer — brongetrouwe highlighting", () => {
  it("markeert letterlijke fragmenten met hun klasse, in tekstvolgorde", () => {
    const segs = segmenteer(BRON, [
      { id: "a", klasse: "Rechtssubject", tekst: "De ontvanger" },
      { id: "b", klasse: "Rechtsbetrekking", tekst: "kan uitstel van betaling verlenen" },
    ]);
    const gemarkeerd = segs.filter((s) => s.klasse);
    expect(gemarkeerd.map((s) => s.tekst)).toEqual([
      "De ontvanger",
      "kan uitstel van betaling verlenen",
    ]);
    expect(gemarkeerd.map((s) => s.klasse)).toEqual(["Rechtssubject", "Rechtsbetrekking"]);
    // de volledige tekst blijft behouden (som van de segmenten == bron)
    expect(segs.map((s) => s.tekst).join("")).toBe(BRON);
  });

  it("markeert een niet-gevonden fragment niet", () => {
    const segs = segmenteer(BRON, [{ klasse: "Rechtssubject", tekst: "komt niet voor" }]);
    expect(segs.some((s) => s.klasse)).toBe(false);
  });

  it("laat het langste fragment winnen bij overlap (geen dubbel-markering)", () => {
    const segs = segmenteer(BRON, [
      { klasse: "Rechtsbetrekking", tekst: "kan uitstel van betaling verlenen" },
      { klasse: "Rechtsobject", tekst: "uitstel van betaling" }, // valt binnen het langere
    ]);
    const gemarkeerd = segs.filter((s) => s.klasse);
    expect(gemarkeerd).toHaveLength(1);
    expect(gemarkeerd[0].klasse).toBe("Rechtsbetrekking");
  });
});
