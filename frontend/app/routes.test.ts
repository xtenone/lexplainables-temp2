import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const APP = join(__dirname);

/** Alle mappen onder `app/`, recursief. */
function mappen(pad: string): string[] {
  const uit: string[] = [];
  for (const naam of readdirSync(pad)) {
    const vol = join(pad, naam);
    if (!statSync(vol).isDirectory()) continue;
    if (naam === "node_modules" || naam.startsWith(".")) continue;
    uit.push(vol, ...mappen(vol));
  }
  return uit;
}

// Next weigert twee verschillend genoemde dynamische segmenten op dezelfde plek
// ("You cannot use different slug names for the same dynamic path"). De build meldt dat wel, maar
// pas na een schone cache — bij ons kwam zo'n conflict daardoor pas op de dev-omgeving boven, waar
// de hele frontend erdoor omviel. Deze controle kost niets en hangt nergens van af.
describe("routestructuur", () => {
  it("gebruikt per niveau hoogstens één naam voor een dynamisch segment", () => {
    const perOuder = new Map<string, Set<string>>();
    for (const map of mappen(APP)) {
      const delen = map.split("/");
      const naam = delen[delen.length - 1];
      if (!naam.startsWith("[")) continue;
      const ouder = delen.slice(0, -1).join("/");
      if (!perOuder.has(ouder)) perOuder.set(ouder, new Set());
      perOuder.get(ouder)!.add(naam);
    }

    const botsingen = [...perOuder.entries()]
      .filter(([, namen]) => namen.size > 1)
      .map(([ouder, namen]) => `${ouder.replace(APP, "app")}: ${[...namen].join(" vs ")}`);

    expect(botsingen).toEqual([]);
  });
});
