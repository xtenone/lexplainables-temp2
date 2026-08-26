import { describe, expect, it } from "vitest";

import { sessieGerevoceerd } from "./sessie";

describe("sessieGerevoceerd", () => {
  it("revoket een token dat vóór de epoch is uitgegeven", () => {
    expect(sessieGerevoceerd(1000, 2000)).toBe(true);
  });

  it("laat een token op/na de epoch staan", () => {
    expect(sessieGerevoceerd(2000, 2000)).toBe(false);
    expect(sessieGerevoceerd(3000, 2000)).toBe(false);
  });

  it("revoket niet zonder epoch (nooit gewijzigd)", () => {
    expect(sessieGerevoceerd(1000, undefined)).toBe(false);
    expect(sessieGerevoceerd(1000, 0)).toBe(false);
  });

  it("behandelt een ontbrekend/niet-numeriek loginAt als 0 (dus gerevoceerd bij een epoch)", () => {
    expect(sessieGerevoceerd(undefined, 2000)).toBe(true);
    expect(sessieGerevoceerd("x", 2000)).toBe(true);
  });
});
