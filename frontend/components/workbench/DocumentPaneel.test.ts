import { describe, expect, it } from "vitest";

import { segmenteer } from "./DocumentPaneel";
import { maakAnker } from "@/lib/selectie";

const BRON = "De ontvanger kan uitstel van betaling verlenen aan de belastingschuldige.";
const HERHAALD = "De ontvanger verleent uitstel. De ontvanger kan dat weigeren.";

/** Alle segmenten samen zijn altijd de hele brontekst — anders raakt er wettekst zoek in beeld. */
function heelGebleven(bron: string, segs: { tekst: string }[]) {
  expect(segs.map((s) => s.tekst).join("")).toBe(bron);
}

describe("segmenteer — alleen de geselecteerde markering", () => {
  const ELEMENTEN = [
    { id: "lang", klasse: "Afleidingsregel", tekst: BRON },
    { id: "kort", klasse: "Rechtsobject", tekst: "uitstel van betaling" },
  ];

  it("toont zonder selectie niets: de tekst blijft schoon", () => {
    const segs = segmenteer(BRON, ELEMENTEN);
    expect(segs.some((s) => s.klasse)).toBe(false);
    heelGebleven(BRON, segs);
  });

  it("toont de geselecteerde markering, ook als die binnen een langere valt", () => {
    // Dit was het probleem: overlappende markeringen kunnen niet naast elkaar bestaan, dus de lange
    // slokte de korte op en aanklikken hielp niet.
    const gemarkeerd = segmenteer(BRON, ELEMENTEN, "kort").filter((s) => s.klasse);
    expect(gemarkeerd.map((s) => s.id)).toEqual(["kort"]);
    expect(gemarkeerd[0].tekst).toBe("uitstel van betaling");
  });

  it("markeert een fragment dat de hele bron beslaat zonder lege randsegmenten", () => {
    const segs = segmenteer(BRON, ELEMENTEN, "lang");
    expect(segs).toHaveLength(1);
    expect(segs[0].klasse).toBe("Afleidingsregel");
  });

  it("houdt de tekst heel rond de markering", () => {
    heelGebleven(BRON, segmenteer(BRON, ELEMENTEN, "kort"));
  });

  it("toont niets als het actieve id niet (meer) bestaat", () => {
    // Bv. na een intrekking: geen willekeurige andere markering oplichten.
    expect(segmenteer(BRON, ELEMENTEN, "weg").some((s) => s.klasse)).toBe(false);
  });

  it("markeert een fragment niet als het niet letterlijk in de tekst staat", () => {
    const segs = segmenteer(BRON, [{ id: "a", klasse: "Rechtssubject", tekst: "komt niet voor" }], "a");
    expect(segs.some((s) => s.klasse)).toBe(false);
    heelGebleven(BRON, segs);
  });

  it("draagt de herkomst mee, zodat de tekst een eigen markering anders kan tonen", () => {
    const segs = segmenteer(BRON, [
      { id: "m", klasse: "Rechtsobject", tekst: "uitstel van betaling", herkomst: "mens" },
    ], "m");
    expect(segs.find((s) => s.klasse)?.herkomst).toBe("mens");
  });
});

// --- ankers: welk voorkomen van een herhaald fragment wordt gemarkeerd? -------------------------

describe("segmenteer — ankers", () => {
  function offsetVanMarkering(segs: { tekst: string; klasse?: string }[]) {
    return segs.slice(0, segs.findIndex((s) => s.klasse)).map((s) => s.tekst).join("").length;
  }

  it("gebruikt het anker om het juiste voorkomen te kiezen", () => {
    // Zonder anker zou "De ontvanger" altijd op positie 0 landen; het anker wijst de tweede aan.
    const tweede = HERHAALD.indexOf("De ontvanger", 1);
    const segs = segmenteer(HERHAALD, [
      { id: "b", klasse: "Rechtssubject", tekst: "De ontvanger",
        anker: maakAnker(HERHAALD, tweede, tweede + 12) },
    ], "b");
    expect(offsetVanMarkering(segs)).toBe(tweede);
  });

  it("valt terug op de omringende tekst als de bron is geschoven", () => {
    // Het anker komt van een oudere versie van de tekst: de hash klopt niet meer en de offsets
    // wijzen naar de verkeerde plek. De context moet het dan alsnog goed krijgen.
    const oud = "Inleiding. " + HERHAALD;
    // let op: lastIndexOf — met indexOf(…, 1) pak je in `oud` nog steeds het EERSTE voorkomen,
    // want "Inleiding. " schuift alles 11 tekens op.
    const tweedeOud = oud.lastIndexOf("De ontvanger");
    const verouderd = maakAnker(oud, tweedeOud, tweedeOud + 12);

    const segs = segmenteer(HERHAALD, [
      { id: "b", klasse: "Rechtssubject", tekst: "De ontvanger", anker: verouderd },
    ], "b");
    expect(offsetVanMarkering(segs)).toBe(HERHAALD.indexOf("De ontvanger", 1));
  });

  it("pakt zonder anker het eerste voorkomen", () => {
    const segs = segmenteer(HERHAALD, [
      { id: "a", klasse: "Rechtssubject", tekst: "De ontvanger" },
    ], "a");
    expect(offsetVanMarkering(segs)).toBe(0);
  });
});
