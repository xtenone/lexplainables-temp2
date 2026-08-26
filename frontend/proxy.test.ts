import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

/** Het matcher-patroon uit `proxy.ts`, uit de bron gelezen in plaats van geïmporteerd.
 *
 *  Importeren kan niet: `proxy.ts` roept `NextAuth()` aan bij het laden en dat trekt `next/server`
 *  mee, dat in de node-omgeving van vitest niet resolvet. Overtypen wil ik nog minder — dan bewaakt
 *  deze test een kopie die naast de echte kan gaan lopen. Dus lezen we de echte regel.
 *
 *  De matcher moet in `proxy.ts` een letterlijke string blijven: Next analyseert hem statisch bij het
 *  bouwen, en een geïmporteerde constante zou daar stilzwijgend kunnen sneuvelen — met de routegate
 *  als inzet. */
const PATROON = (() => {
  const bron = readFileSync(new URL("./proxy.ts", import.meta.url), "utf8");
  const m = bron.match(/matcher:\s*\[\s*"([^"]+)"/);
  if (!m) throw new Error("Geen matcher-string gevonden in proxy.ts");
  return m[1].replace(/\\\\/g, "\\"); // bron-escape (\\.) → regex (\.)
})();

/** Bewaakt de routegate dit pad, of valt het buiten de matcher?
 *
 *  Dit legt de bedoeling van het patroon vast; Next's eigen compilatie bootst het niet na. Precies
 *  die bedoeling was stilzwijgend verkeerd. */
function bewaakt(pad: string): boolean {
  return new RegExp(`^${PATROON}$`).test(pad);
}

describe("routegate-matcher", () => {
  it("bewaakt de pagina's en de BFF-routes", () => {
    expect(bewaakt("/")).toBe(true);
    expect(bewaakt("/workbench")).toBe(true);
    expect(bewaakt("/instellingen/beheer")).toBe(true);
    expect(bewaakt("/api/gesprekken")).toBe(true);
    expect(bewaakt("/api/admin/users")).toBe(true);
  });

  it("bewaakt ook een BFF-pad dat op een bestandsnaam lijkt", () => {
    // Dit was het gat: zonder eind-anker matchte `.*\.png` elk pad met ".png" eríń, dus liep
    // /api/gesprekken/abc.png buiten de sessie-, rol- en Origin-controle om. Een dynamische
    // route-parameter mag er nu eenmaal uitzien als een bestandsnaam.
    expect(bewaakt("/api/gesprekken/abc.png")).toBe(true);
    expect(bewaakt("/api/admin/users/foo.svg")).toBe(true);
    expect(bewaakt("/api/annotatie/documenten/iw-art9.ico/elementen")).toBe(true);
  });

  it("laat Auth.js' eigen routes en de Next-interne paden met rust", () => {
    expect(bewaakt("/api/auth/session")).toBe(false);
    expect(bewaakt("/_next/static/chunks/main.js")).toBe(false);
    expect(bewaakt("/_next/image")).toBe(false);
  });

  it("laat echte statische bestanden met rust", () => {
    expect(bewaakt("/favicon.ico")).toBe(false);
    expect(bewaakt("/belastingdienst-logo.svg")).toBe(false);
    expect(bewaakt("/apple-touch-icon.png")).toBe(false);
    expect(bewaakt("/manifest.webmanifest")).toBe(false);
  });
});
