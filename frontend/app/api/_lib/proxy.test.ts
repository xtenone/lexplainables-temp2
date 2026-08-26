import { describe, expect, it } from "vitest";
import { rewriteLocation } from "./proxy";

describe("rewriteLocation", () => {
  it("herschrijft een upstream Location naar de eigen BFF-route", () => {
    expect(rewriteLocation("/v1/projects/bwbr1-art9")).toBe("/api/projects/bwbr1-art9");
  });

  it("werkt ook met een absolute upstream-URL", () => {
    expect(rewriteLocation("http://wetsanalyse-api:3000/v1/projects/abc")).toBe("/api/projects/abc");
  });

  it("laat een onbekend pad ongemoeid", () => {
    expect(rewriteLocation("/health")).toBe("/health");
  });
});
