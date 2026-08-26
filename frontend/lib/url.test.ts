import { describe, expect, it } from "vitest";
import { bronHref, normaliseerJci, pathSegment, veiligPad } from "./url";

describe("normaliseerJci", () => {
  it("voegt &z= toe (gelijk aan &g=) als alleen &g= aanwezig is", () => {
    expect(normaliseerJci("jci1.3:c:BWBR0002320&artikel=25&g=2026-04-11")).toBe(
      "jci1.3:c:BWBR0002320&artikel=25&z=2026-04-11&g=2026-04-11",
    );
    expect(normaliseerJci("jci1.3:c:BWBR0002320&artikel=25&lid=1&g=2026-04-11")).toBe(
      "jci1.3:c:BWBR0002320&artikel=25&lid=1&z=2026-04-11&g=2026-04-11",
    );
  });

  it("laat een jci met al een &z= ongemoeid", () => {
    const jci = "jci1.3:c:BWBR0002320&artikel=52a&z=2026-04-11&g=2026-04-11";
    expect(normaliseerJci(jci)).toBe(jci);
  });

  it("laat een jci zonder datum ongemoeid (kale kruisverwijzing)", () => {
    expect(normaliseerJci("jci1.3:c:BWBR0005537&artikel=7:2")).toBe(
      "jci1.3:c:BWBR0005537&artikel=7:2",
    );
  });
});

describe("pathSegment", () => {
  it("encodeert een kale slug met gereserveerde tekens precies één keer", () => {
    // Artikel 4:86 → slug met ':' → moet %3A worden, niet %253A.
    expect(pathSegment("bwbr0005537-art4:86-3")).toBe("bwbr0005537-art4%3A86-3");
  });

  it("dubbel-encodeert een al-geëncodeerde param niet (Next levert params ge-encode aan)", () => {
    expect(pathSegment("bwbr0005537-art4%3A86-3")).toBe("bwbr0005537-art4%3A86-3");
  });

  it("is idempotent: tweemaal toepassen geeft hetzelfde resultaat", () => {
    const once = pathSegment("bwbr0005537-art4:86-3");
    expect(pathSegment(once)).toBe(once);
  });

  it("laat een gewone slug zonder gereserveerde tekens ongemoeid", () => {
    expect(pathSegment("bwbr0004770-art9-lid2")).toBe("bwbr0004770-art9-lid2");
  });

  it("codeert spaties (bv. een profielnaam) correct", () => {
    expect(pathSegment("Mijn Profiel")).toBe("Mijn%20Profiel");
    expect(pathSegment("Mijn%20Profiel")).toBe("Mijn%20Profiel");
  });
});

describe("bronHref", () => {
  it("maakt van een jci-uri een wetten.overheid.nl-deeplink", () => {
    expect(bronHref("jci1.3:c:BWBR0004770&artikel=9")).toBe(
      "https://wetten.overheid.nl/jci1.3:c:BWBR0004770&artikel=9",
    );
  });

  it("laat een complete wetten.overheid.nl-URL ongemoeid", () => {
    expect(bronHref("https://wetten.overheid.nl/BWBR0004770")).toBe(
      "https://wetten.overheid.nl/BWBR0004770",
    );
  });

  it("weigert een http(s)-URL naar een vreemde host (phishing/host-pinning) → undefined", () => {
    expect(bronHref("https://phish.example/BWBR0004770")).toBeUndefined();
    expect(bronHref("http://wetten.overheid.nl.evil.example/x")).toBeUndefined();
  });

  it("vult &z= aan bij een jci met alleen &g= (deeplink landt zo op de bepaling)", () => {
    expect(bronHref("jci1.3:c:BWBR0002320&artikel=25&lid=1&g=2026-04-11")).toBe(
      "https://wetten.overheid.nl/jci1.3:c:BWBR0002320&artikel=25&lid=1&z=2026-04-11&g=2026-04-11",
    );
  });

  it("weigert een javascript:-URL (XSS) → undefined", () => {
    expect(bronHref("javascript:alert(document.cookie)")).toBeUndefined();
    expect(bronHref("JavaScript:alert(1)")).toBeUndefined();
  });

  it("vertaalt een graaf-IRI naar de deeplink van de bepaling", () => {
    // De agent levert vindplaatsen ook als IRI uit de kennisgraaf. Die werden eerder achter
    // wetten.overheid.nl geplakt — een klikbare link naar een 404.
    expect(bronHref("urn:bwb:BWBR0004770:artikel:9")).toBe(
      "https://wetten.overheid.nl/jci1.3:c:BWBR0004770&artikel=9",
    );
    expect(bronHref("urn:bwb:BWBR0004770:artikel:2:lid:1")).toBe(
      "https://wetten.overheid.nl/jci1.3:c:BWBR0004770&artikel=2&lid=1",
    );
  });

  it("vertaalt de IRI van een hele wet naar de regelingpagina", () => {
    expect(bronHref("urn:bwb:BWBR0004770")).toBe(
      "https://wetten.overheid.nl/BWBR0004770",
    );
  });

  it("maakt van een kaal BWB-id een regelingpagina", () => {
    expect(bronHref("BWBR0004770")).toBe("https://wetten.overheid.nl/BWBR0004770");
  });

  it("geeft geen link bij een IRI die niet te citeren is", () => {
    // Interne knopen (id/, ref/, begrip/, graph/) hebben geen publieke vindplaats. Dan liever geen
    // link dan een link die ergens anders uitkomt.
    expect(bronHref("urn:bwb:BWBR0004770:id:art9-lid1")).toBeUndefined();
    expect(bronHref("urn:bwb:ref:9f2c1a")).toBeUndefined();
    expect(bronHref("urn:bwb:begrip:belastingschuldige")).toBeUndefined();
  });

  it("weigert een IRI-achtige URL op een vreemde host", () => {
    expect(bronHref("https://evil.example/bwb/BWBR0004770/artikel/9")).toBeUndefined();
  });

  it("weigert een data:-URL en lege invoer → undefined", () => {
    expect(bronHref("data:text/html,<script>alert(1)</script>")).toBeUndefined();
    expect(bronHref("")).toBeUndefined();
    expect(bronHref(undefined)).toBeUndefined();
  });
});

describe("veiligPad", () => {
  const eigen = "https://app.example";

  it("houdt pad en query van een callbackUrl op het eigen origin", () => {
    expect(veiligPad("/projecten/abc?tab=rapport", eigen)).toBe("/projecten/abc?tab=rapport");
  });

  it("werkt met een absolute URL op het eigen origin", () => {
    expect(veiligPad(`${eigen}/beheer`, eigen)).toBe("/beheer");
  });

  it("weigert een sprong naar een andere host", () => {
    expect(veiligPad("https://evil.example/pad", eigen)).toBe("/");
  });

  it("weigert een protocol-relatief pad", () => {
    expect(veiligPad("//evil.example", eigen)).toBe("/");
  });

  it("valt zonder callbackUrl terug op de startpagina", () => {
    expect(veiligPad(null, eigen)).toBe("/");
  });
});
