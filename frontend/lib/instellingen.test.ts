import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { INSTELLINGEN_TABS, isAdminTab, padVanTab, tabUitPad } from "./instellingen";

const WORTEL = join(__dirname, "..");
const lees = (p: string) => readFileSync(join(WORTEL, p), "utf8");

/** Is dit bestand een client component? Kijkt naar de *directive* op de eerste zinvolle regel, niet
 *  naar de tekst ergens in het bestand — anders telt een toelichting die "use client" noemt al mee. */
function isClientComponent(src: string): boolean {
  const eerste = src.split("\n").find((r) => r.trim() !== "");
  return /^["']use client["'];?$/.test((eerste ?? "").trim());
}

describe("tabUitPad", () => {
  it("leest de tab uit de padsegmenten", () => {
    expect(tabUitPad(["account"])).toBe("account");
    expect(tabUitPad(["beheer", "gebruikers"])).toBe("gebruikers");
  });

  it("valt terug op account bij leeg of onbekend", () => {
    expect(tabUitPad(undefined)).toBe("account");
    expect(tabUitPad([])).toBe("account");
    expect(tabUitPad(["bestaat", "niet"])).toBe("account");
  });
});

describe("padVanTab", () => {
  it("is het omgekeerde van tabUitPad", () => {
    expect(padVanTab("gebruikers")).toBe("/instellingen/beheer/gebruikers");
    expect(padVanTab("account")).toBe("/instellingen/account");
  });
});

describe("isAdminTab", () => {
  it("markeert alleen de beheer-tabs", () => {
    expect(isAdminTab("account")).toBe(false);
    expect(isAdminTab("beveiliging")).toBe(false);
    expect(isAdminTab("berichten")).toBe(false);
    for (const t of ["modelprofielen", "gebruikers", "api-tokens", "berichtenbeheer", "feedback"] as const) {
      expect(isAdminTab(t)).toBe(true);
    }
  });

  // De rolgate in auth.config.ts is één prefix-check op /instellingen/beheer. Een admin-tab die
  // buiten dat pad gaat wonen, is dus onbewaakt: de tabkolom verbergt hem wel voor een analist,
  // maar de directe URL komt er ongehinderd door. Daarom hier de koppeling zelf bewaken in plaats
  // van een lijstje tabnamen — die veroudert bij elke nieuwe tab.
  it("elke admin-tab staat onder beheer/ (anders valt de rolgate weg)", () => {
    for (const tab of INSTELLINGEN_TABS) {
      expect(tab.admin, `tab '${tab.key}' (pad '${tab.pad}')`).toBe(tab.pad.startsWith("beheer/"));
    }
  });

  it("auth.config.ts bewaakt die prefix nog steeds", () => {
    expect(lees("auth.config.ts")).toContain('path.startsWith("/instellingen/beheer")');
  });
});

// Deze helpers worden vanuit server components aangeroepen (de rolgate op beide instellingen-routes).
// Staan ze in een "use client"-module, dan compileert en lint het prima maar crasht de route pas bij
// het renderen: "Attempted to call tabUitPad() from the server but tabUitPad is on the client".
// Die grens is alleen met een structuurcontrole te bewaken.
describe("RSC-grens", () => {
  it("de gedeelde module is niet client-only", () => {
    expect(isClientComponent(lees("lib/instellingen.ts"))).toBe(false);
  });

  it("de server components halen de helpers uit de gedeelde module", () => {
    for (const p of [
      "app/instellingen/[[...tab]]/page.tsx",
      "app/@modal/(.)instellingen/[[...tab]]/page.tsx",
    ]) {
      const src = lees(p);
      expect(isClientComponent(src)).toBe(false);
      expect(src).toMatch(/import \{[^}]*tabUitPad[^}]*\} from "@\/lib\/instellingen"/);
    }
  });
});
