import { afterEach, describe, expect, it, vi } from "vitest";
import { log, logger } from "./logger";

/** Vang de JSON-regels op die de logger naar stdout schrijft. */
function vangOp(fn: () => void): Record<string, unknown>[] {
  const regels: Record<string, unknown>[] = [];
  const spy = vi.spyOn(process.stdout, "write").mockImplementation((chunk: unknown) => {
    regels.push(JSON.parse(String(chunk)));
    return true;
  });
  try {
    fn();
  } finally {
    spy.mockRestore();
  }
  return regels;
}

afterEach(() => {
  delete process.env.LOG_LEVEL;
});

describe("logger", () => {
  it("schrijft de MCP-logvorm (ts/niveau/categorie/bericht + velden)", () => {
    const [regel] = vangOp(() => logger.info("hallo", { bwbId: "BWBR1" }));
    expect(regel.niveau).toBe("info");
    expect(regel.categorie).toBe("functioneel");
    expect(regel.bericht).toBe("hallo");
    expect(regel.bwbId).toBe("BWBR1");
    expect(String(regel.ts)).toMatch(/Z$/); // UTC-ISO
  });

  it("redacteert geheime velden", () => {
    const [regel] = vangOp(() =>
      log("warn", "security", "poging", {
        token: "geheim",
        secret: "x",
        authorization: "Bearer y",
        bwbId: "BWBR1",
      }),
    );
    expect(regel.token).toBeUndefined();
    expect(regel.secret).toBeUndefined();
    expect(regel.authorization).toBeUndefined();
    expect(regel.bwbId).toBe("BWBR1");
  });

  it("laat null/undefined-velden weg", () => {
    const [regel] = vangOp(() => logger.info("x", { leeg: null, ook: undefined, gevuld: 3 }));
    expect("leeg" in regel).toBe(false);
    expect("ook" in regel).toBe(false);
    expect(regel.gevuld).toBe(3);
  });

  it("respecteert LOG_LEVEL (debug onder de drempel wordt niet geschreven)", () => {
    process.env.LOG_LEVEL = "info";
    const regels = vangOp(() => logger.debug("stil"));
    expect(regels).toHaveLength(0);
  });
});
