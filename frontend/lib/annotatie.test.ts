import { describe, expect, it } from "vitest";
import { documentStatusLabel } from "./annotatie";

describe("documentStatusLabel", () => {
  it("mapt de drie documentstatussen naar NL-labels", () => {
    expect(documentStatusLabel("in_review")).toBe("In behandeling");
    expect(documentStatusLabel("geaccordeerd")).toBe("Geaccordeerd");
    expect(documentStatusLabel("gepromoveerd")).toBe("In de graaf");
  });
});
