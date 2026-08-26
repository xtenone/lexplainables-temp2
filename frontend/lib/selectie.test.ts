import { describe, expect, it } from "vitest";

import { bronHash, lidUitOffset, maakAnker, offsetUit, snapSelectie } from "./selectie";

const BRON = "De ontvanger kan uitstel verlenen. Dat mag hij weigeren.";

describe("offsetUit", () => {
  it("telt de lengtes van de voorgaande tekstknopen op", () => {
    // De browser geeft (knoop, offset-daarbinnen); wij rekenen naar één offset in de hele bron.
    expect(offsetUit([10, 20, 5], 0, 3)).toBe(3);
    expect(offsetUit([10, 20, 5], 1, 4)).toBe(14);
    expect(offsetUit([10, 20, 5], 2, 0)).toBe(30);
  });

  it("blijft binnen de perken bij een knoopindex voorbij de lijst", () => {
    expect(offsetUit([10], 5, 2)).toBe(12);
  });
});

describe("snapSelectie", () => {
  it("haalt meegesleepte spaties en leestekens van de randen", () => {
    // Een muisselectie pakt bijna altijd te veel mee; het fragment moet letterlijk terugvindbaar zijn.
    const ruw = BRON.indexOf(" kan uitstel verlenen.");
    const { start, eind } = snapSelectie(BRON, ruw, ruw + " kan uitstel verlenen.".length);
    expect(BRON.slice(start, eind)).toBe("kan uitstel verlenen");
  });

  it("draait een omgekeerde selectie om (van rechts naar links slepen)", () => {
    const { start, eind } = snapSelectie(BRON, 12, 3);
    expect(start).toBeLessThan(eind);
    expect(BRON.slice(start, eind)).toBe("ontvanger");
  });

  it("geeft een leeg bereik als er alleen witruimte is geselecteerd", () => {
    const spatie = BRON.indexOf(" ");
    const { start, eind } = snapSelectie(BRON, spatie, spatie + 1);
    expect(start).toBe(eind);
  });

  it("klemt buiten de tekst vallende posities af", () => {
    const { start, eind } = snapSelectie(BRON, -5, BRON.length + 99);
    expect(start).toBe(0);
    expect(eind).toBe(BRON.length - 1); // de slotpunt gaat eraf
  });
});

describe("maakAnker", () => {
  it("legt positie, context en een vingerafdruk van de bron vast", () => {
    const start = BRON.indexOf("uitstel");
    const anker = maakAnker(BRON, start, start + 7, "1");
    expect(BRON.slice(anker.start, anker.eind)).toBe("uitstel");
    expect(anker.voor.endsWith("kan ")).toBe(true);
    expect(anker.na.startsWith(" verlenen")).toBe(true);
    expect(anker.bron_hash).toBe(bronHash(BRON));
    expect(anker.lid).toBe("1");
  });
});

describe("bronHash", () => {
  it("verschilt zodra de tekst verandert — dat is het hele punt", () => {
    expect(bronHash(BRON)).toBe(bronHash(BRON));
    expect(bronHash(BRON)).not.toBe(bronHash(BRON + " "));
  });
});

describe("lidUitOffset", () => {
  const regels = [
    { lid: "1", regel: "1. Eerste lid tekst." },
    { lid: "2", regel: "2. Tweede lid tekst." },
    { lid: "3", regel: "3. Derde lid." },
  ];

  it("wijst een offset toe aan het juiste lid", () => {
    // De bron is de regels aaneengeschakeld met "\n\n", dus tussen elke regel zitten twee tekens.
    expect(lidUitOffset(regels, 0)).toBe("1");
    expect(lidUitOffset(regels, 19)).toBe("1");
    expect(lidUitOffset(regels, 22)).toBe("2");
    expect(lidUitOffset(regels, 44)).toBe("3");
  });

  it("geeft het lidnummer terug, niet de plek in de lijst", () => {
    // Een op één lid afgebakend document levert alléén dat lid — de index is dan 0 en het
    // lidnummer 3. Vroeger kwam hier "1" uit en werd de markering op het verkeerde lid vastgelegd.
    const alleenLid3 = [{ lid: "3", regel: "3. De ontvanger kan uitstel verlenen." }];
    expect(lidUitOffset(alleenLid3, 0)).toBe("3");
    expect(lidUitOffset(alleenLid3, 30)).toBe("3");
  });

  it("kan overweg met een lid dat geen getal is", () => {
    // Ingevoegde leden heten 2a, 2b … — daar loopt tellen sowieso stuk.
    const metLetterlid = [
      { lid: "1", regel: "1. Eerste." },
      { lid: "2a", regel: "2a. Ingevoegd." },
      { lid: "3", regel: "3. Derde." },
    ];
    expect(lidUitOffset(metLetterlid, 12)).toBe("2a");
    expect(lidUitOffset(metLetterlid, 30)).toBe("3");
  });

  it("geeft leeg terug bij een artikel zonder genummerde leden", () => {
    expect(lidUitOffset([{ lid: "", regel: "De ontvanger kan uitstel verlenen." }], 3)).toBe("");
  });

  it("geeft leeg terug voorbij de laatste regel", () => {
    expect(lidUitOffset(regels, 9999)).toBe("");
  });
});
