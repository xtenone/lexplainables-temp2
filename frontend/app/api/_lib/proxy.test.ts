import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

// De BFF-proxy praat met de echte API; hier vervangen we alleen `fetch`. De env-waarden zetten we
// vóór de import, want `lib/config.ts` leest ze bij de eerste aanroep en cachet het token.
process.env.API_BASE_URL = "http://api.test";
process.env.API_TOKEN = "test-token";

let proxy: typeof import("./proxy").proxy;

beforeAll(async () => {
  ({ proxy } = await import("./proxy"));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

/** Een upstream die de verbinding aanneemt maar nooit antwoordt — precies het geval waar Node's
 *  `fetch` uit zichzelf eeuwig op blijft wachten. Rejecten doet hij alleen op het abort-signaal. */
function hangendeUpstream() {
  return vi.fn((_url: string, init?: RequestInit) => {
    return new Promise<Response>((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        const fout = new Error("The operation was aborted due to timeout");
        fout.name = "TimeoutError";
        reject(fout);
      });
    });
  });
}

describe("proxy — timeout", () => {
  it("geeft 504 met een leesbare reden als de upstream niet op tijd antwoordt", async () => {
    vi.stubGlobal("fetch", hangendeUpstream());

    const res = await proxy("/v1/annotatie/documenten", { timeoutMs: 30 });

    expect(res.status).toBe(504);
    expect(await res.json()).toEqual({ detail: "De API antwoordde niet binnen 30 ms." });
  });

  it("geeft het abort-signaal door aan de upstream", async () => {
    const nep = hangendeUpstream();
    vi.stubGlobal("fetch", nep);

    await proxy("/v1/annotatie/documenten", { timeoutMs: 30 });

    // Zonder signal zou de fetch nooit afgebroken worden en bleef deze test hangen; expliciet
    // controleren zodat een refactor die het signal laat vallen hier stukloopt in plaats van in
    // productie.
    expect(nep.mock.calls[0][1]?.signal).toBeInstanceOf(AbortSignal);
  });

  it("houdt een onbereikbare API op 502 — dat is iets anders dan te traag", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fetch failed"))));

    const res = await proxy("/v1/annotatie/documenten");

    expect(res.status).toBe(502);
    expect((await res.json()).detail).toContain("API onbereikbaar");
  });

  it("laat een normaal antwoord ongemoeid", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ ok: true }), {
            status: 201,
            headers: { "Content-Type": "application/json", Location: "/v1/x/1" },
          }),
        ),
      ),
    );

    const res = await proxy("/v1/annotatie/documenten", { method: "POST", body: "{}" });

    expect(res.status).toBe(201);
    expect(res.headers.get("Location")).toBe("/v1/x/1");
    expect(await res.json()).toEqual({ ok: true });
  });
});
