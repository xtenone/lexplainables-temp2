import { describe, expect, it } from "vitest";
import {
  definitieveStroomfout, herstelWachttijd, naEenGebrokenStream, onthoudRun, standVanVorigeRun,
  vergeetRun,
} from "./lopendeRun";

describe("standVanVorigeRun", () => {
  it("zegt niets als er geen beurt openstond", () => {
    expect(standVanVorigeRun(undefined, [])).toBe("geen");
  });

  it("herkent een beurt die gewoon is afgerond terwijl je weg was", () => {
    // Die verdwijnt óók uit het run-register (na de bewaartermijn), maar heeft wél een bericht
    // achtergelaten. Zonder dit onderscheid zou elke normale afloop als "afgebroken" gemeld worden.
    expect(standVanVorigeRun("run-1", ["run-0", "run-1"])).toBe("afgerond");
  });

  it("herkent een beurt die verdwenen is door een herstart", () => {
    // Geen run meer én geen bericht: het register is leeg. Dat hoort gezegd te worden, in plaats
    // van een gesprek dat halverwege ophoudt zonder uitleg.
    expect(standVanVorigeRun("run-1", ["run-0"])).toBe("verdwenen");
    expect(standVanVorigeRun("run-1", [])).toBe("verdwenen");
  });
});

describe("onthoudRun / vergeetRun", () => {
  it("houdt hoogstens één lopende beurt per gesprek bij", () => {
    let runs = onthoudRun({}, "g1", "run-1");
    runs = onthoudRun(runs, "g1", "run-2");
    expect(runs).toEqual({ g1: "run-2" });
  });

  it("houdt gesprekken uit elkaar", () => {
    const runs = onthoudRun(onthoudRun({}, "g1", "run-1"), "g2", "run-2");
    expect(vergeetRun(runs, "g1")).toEqual({ g2: "run-2" });
  });

  it("vergeten van iets dat er niet staat is geen fout", () => {
    expect(vergeetRun({ g1: "run-1" }, "g9")).toEqual({ g1: "run-1" });
  });
});

describe("naEenGebrokenStream", () => {
  it("negeert een stream die we zelf afbraken", () => {
    // Unmount of van gesprek wisselen: de run draait door, er valt niets te melden of te herstellen.
    expect(naEenGebrokenStream(true, true, false)).toBe("negeren");
  });

  it("haakt opnieuw aan als de verbinding wegvalt", () => {
    // Dit is het geval dat bij een deploy optrad: de frontend-container werd vervangen, het tabblad
    // zag "network error", en de beurt liep ondertussen door en slaagde.
    expect(naEenGebrokenStream(false, true, false)).toBe("opnieuw");
  });

  it("blijft aanhaken, ook na een eerdere mislukte poging", () => {
    // Er is geen cap: de melding staat in beeld en de wachttijd loopt op, dus doorproberen is geen
    // molen. Eén poging was te weinig voor een herstart van graph-qa.
    expect(naEenGebrokenStream(false, true, false)).toBe("opnieuw");
  });

  it("meldt een fout waar opnieuw aanhaken niet bij helpt", () => {
    // De agent stuurde zelf een fout, of de run bestaat niet meer: replay levert hetzelfde.
    expect(naEenGebrokenStream(false, true, true)).toBe("melden");
  });

  it("doet niets meer als het venster weg is", () => {
    // Zonder venster is er niemand om iets aan te tonen; de run draait gewoon door bij de agent.
    expect(naEenGebrokenStream(false, false, false)).toBe("negeren");
    expect(naEenGebrokenStream(false, false, true)).toBe("negeren");
  });
});

describe("definitieveStroomfout", () => {
  it("herkent een fout die de agent zelf stuurde", () => {
    // Zelfde status als "BFF kon graph-qa niet bereiken" (502); alleen `agentFout` scheidt ze.
    expect(definitieveStroomfout({ status: 502, detail: "x", agentFout: true })).toBe(true);
    expect(definitieveStroomfout({ status: 502, detail: "x" })).toBe(false);
  });

  it("herkent een run die niet (meer) van jou is of niet bestaat", () => {
    for (const status of [401, 403, 404]) {
      expect(definitieveStroomfout({ status, detail: "x" })).toBe(true);
    }
  });

  it("houdt netwerkfouten en 5xx tijdelijk", () => {
    expect(definitieveStroomfout({ status: 0, detail: "De verbinding viel stil." })).toBe(false);
    expect(definitieveStroomfout({ status: 503, detail: "x" })).toBe(false);
    expect(definitieveStroomfout(new TypeError("Failed to fetch"))).toBe(false);
    expect(definitieveStroomfout(null)).toBe(false);
  });
});

describe("herstelWachttijd", () => {
  it("loopt op", () => {
    expect(herstelWachttijd(0)).toBe(1500);
    expect(herstelWachttijd(1)).toBe(3000);
    expect(herstelWachttijd(2)).toBe(6000);
    expect(herstelWachttijd(3)).toBe(12_000);
  });

  it("heeft een plafond, zodat herstel vlot blijft", () => {
    expect(herstelWachttijd(4)).toBe(15_000);
    expect(herstelWachttijd(50)).toBe(15_000);
  });
});
