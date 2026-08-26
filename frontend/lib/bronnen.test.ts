import { describe, expect, it } from "vitest";
import { vindplaatsText } from "./bronnen";

describe("vindplaatsText", () => {
  const labels = {
    br1: "Leidraad Invordering 2008 art. 9.5",
    br2: "Invorderingswet 1990 art. 9 lid 1",
    br3: "Leidraad Invordering 2008 art. 7a",
  };

  it("plakt een kaal lid-nummer netjes aan", () => {
    expect(vindplaatsText([{ bron_id: "br1", lid: "1" }], labels)).toBe(
      "Leidraad Invordering 2008 art. 9.5 lid 1",
    );
  });

  it("verdubbelt de lid-prefix niet bij een al geprefixte waarde ('lid 1')", () => {
    // Regressie: data bevat "lid 1" i.p.v. "1"; mag geen "lid lid 1" worden.
    expect(vindplaatsText([{ bron_id: "br1", lid: "lid 1" }], labels)).toBe(
      "Leidraad Invordering 2008 art. 9.5 lid 1",
    );
  });

  it("herhaalt het lid niet als het bron-label het al bevat (bron op lid-niveau)", () => {
    expect(vindplaatsText([{ bron_id: "br2", lid: "lid 1" }], labels)).toBe(
      "Invorderingswet 1990 art. 9 lid 1",
    );
    expect(vindplaatsText([{ bron_id: "br2", lid: "1" }], labels)).toBe(
      "Invorderingswet 1990 art. 9 lid 1",
    );
  });

  it("voegt geen suffix toe bij een lid-loos artikel", () => {
    expect(vindplaatsText([{ bron_id: "br3", lid: "" }], labels)).toBe(
      "Leidraad Invordering 2008 art. 7a",
    );
  });

  it("verwart 'art. 9.1' niet met een lid", () => {
    const l = { br4: "Leidraad Invordering 2008 art. 9.1" };
    expect(vindplaatsText([{ bron_id: "br4", lid: "1" }], l)).toBe(
      "Leidraad Invordering 2008 art. 9.1 lid 1",
    );
  });

  it("combineert meerdere vindplaatsen met puntkomma", () => {
    expect(
      vindplaatsText([{ bron_id: "br1", lid: "lid 1" }, { bron_id: "br2", lid: "lid 1" }], labels),
    ).toBe("Leidraad Invordering 2008 art. 9.5 lid 1; Invorderingswet 1990 art. 9 lid 1");
  });

  it("valt terug op het bron_id als er geen label is", () => {
    expect(vindplaatsText([{ bron_id: "onbekend", lid: "2" }], {})).toBe("onbekend lid 2");
  });

  it("geeft lege string bij geen vindplaatsen", () => {
    expect(vindplaatsText([], labels)).toBe("");
    expect(vindplaatsText(undefined, labels)).toBe("");
  });
});
