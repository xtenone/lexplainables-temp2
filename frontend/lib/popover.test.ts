import { describe, expect, it } from "vitest";

import { klemHorizontaal, plaatsPopover } from "./popover";

const POPOVER = { breedte: 320, hoogte: 280 };
const SCHERM = { breedte: 400, hoogte: 800 };

describe("plaatsPopover", () => {
  it("hangt onder de selectie als het daar past", () => {
    const p = plaatsPopover({ midden: 200, boven: 100, onder: 120 }, POPOVER, SCHERM);
    expect(p).toEqual({ left: 40, top: 128, boven: false });
  });

  it("klapt naar boven als het er onder niet meer past", () => {
    // Selectie onderin een telefoonscherm: onder de selectie is nog 100 px, de popover is 280 hoog.
    // Dit was de bug — de klasse-lijst viel buiten beeld en `position: fixed` scrolt niet mee.
    const p = plaatsPopover({ midden: 200, boven: 660, onder: 700 }, POPOVER, SCHERM);
    expect(p.boven).toBe(true);
    expect(p.top).toBe(660 - 280 - 8);
    expect(p.top + POPOVER.hoogte).toBeLessThan(660);
  });

  it("valt terug op de bovenrand als het nergens past", () => {
    const laag = { breedte: 400, hoogte: 320 };
    const p = plaatsPopover({ midden: 200, boven: 150, onder: 200 }, POPOVER, laag);
    expect(p.top).toBe(8);
    expect(p.top + POPOVER.hoogte).toBeLessThanOrEqual(laag.hoogte);
  });

  it("houdt de popover binnen de linker- en rechterrand", () => {
    expect(plaatsPopover({ midden: 5, boven: 100, onder: 120 }, POPOVER, SCHERM).left).toBe(8);
    expect(plaatsPopover({ midden: 395, boven: 100, onder: 120 }, POPOVER, SCHERM).left).toBe(
      400 - 320 - 8,
    );
  });

  it("centreert op de selectie als daar ruimte voor is", () => {
    const breed = { breedte: 1400, hoogte: 900 };
    expect(plaatsPopover({ midden: 700, boven: 300, onder: 320 }, POPOVER, breed).left).toBe(540);
  });
});

describe("klemHorizontaal — een popover blijft binnen het scherm", () => {
  it("schuift naar rechts als het paneel links uitsteekt", () => {
    // De exportlijst uit de schermafdruk: 256px breed, rechts uitgelijnd op een knop die zelf al
    // rechts staat, op een scherm van 414px. Linkerrand op -40 → de eerste tekens vielen weg.
    expect(klemHorizontaal({ left: -40, breedte: 256 }, 414)).toBe(48);
  });

  it("schuift naar links als het paneel rechts uitsteekt", () => {
    expect(klemHorizontaal({ left: 200, breedte: 256 }, 414)).toBe(414 - 8 - 456);
  });

  it("laat een paneel dat past met rust", () => {
    expect(klemHorizontaal({ left: 100, breedte: 256 }, 414)).toBe(0);
  });

  it("respecteert de marge langs de rand", () => {
    expect(klemHorizontaal({ left: 2, breedte: 100 }, 414)).toBe(6);
    expect(klemHorizontaal({ left: 8, breedte: 100 }, 414)).toBe(0);
  });

  it("kiest de linkerrand als het paneel breder is dan het scherm", () => {
    // Liever het begin van de tekst lezen dan het eind: dan is tenminste duidelijk wát er staat.
    expect(klemHorizontaal({ left: -20, breedte: 400 }, 320)).toBe(28);
  });
});
