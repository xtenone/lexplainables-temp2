import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

// De BFF praat met de echte API; hier vervangen we alleen `fetch`. De env-waarden moeten vóór de
// import staan, want `lib/config.ts` leest ze bij de eerste aanroep en cachet het token.
process.env.API_BASE_URL = "http://api.test";
process.env.API_TOKEN = "test-token";

vi.mock("@/app/api/_lib/session", () => ({
  sessionUserId: async () => "gebruiker-a",
  geenSessie: () => Response.json({ detail: "Niet ingelogd." }, { status: 401 }),
}));

let POST: typeof import("./route").POST;

beforeAll(async () => {
  ({ POST } = await import("./route"));
});

afterEach(() => vi.unstubAllGlobals());

function nepUpstream() {
  return vi.fn((_url: string, _init?: RequestInit) =>
    Promise.resolve(
      new Response(new Uint8Array([0x25, 0x50, 0x44, 0x46]), {
        status: 200,
        headers: {
          "content-type": "application/pdf",
          "content-disposition": 'attachment; filename="annotatie-BWBR1-art9-abc.pdf"',
        },
      }),
    ),
  );
}

const params = { params: Promise.resolve({ slug: "abc" }) };

function verzoek(query: string) {
  return new Request(`http://app.test/api/annotatie/documenten/abc/export${query}`, {
    method: "POST",
    body: JSON.stringify({ leden: [{ lid: "1", tekst: "De ontvanger verleent uitstel." }] }),
  });
}

describe("export-route", () => {
  it("stuurt het gevraagde formaat door naar de upstream", async () => {
    const nep = nepUpstream();
    vi.stubGlobal("fetch", nep);

    await POST(verzoek("?formaat=csv"), params);

    // Een proxyroute die de queryparam laat vallen faalt stil: je krijgt dan altijd het
    // default-formaat terug zonder dat er iets misgaat.
    expect(nep.mock.calls[0][0]).toBe(
      "http://api.test/v1/annotatie/documenten/abc/export?formaat=csv",
    );
  });

  it("geeft Content-Disposition door, anders landt de download naamloos", async () => {
    vi.stubGlobal("fetch", nepUpstream());

    const res = await POST(verzoek("?formaat=pdf"), params);

    expect(res.status).toBe(200);
    expect(res.headers.get("content-type")).toBe("application/pdf");
    expect(res.headers.get("content-disposition")).toContain('filename="annotatie-BWBR1-art9-abc.pdf"');
  });

  it("weigert een onbekend formaat zonder de upstream te bellen", async () => {
    const nep = nepUpstream();
    vi.stubGlobal("fetch", nep);

    const res = await POST(verzoek("?formaat=docx"), params);

    expect(res.status).toBe(422);
    expect(nep).not.toHaveBeenCalled();
  });

  it("valt zonder formaat terug op pdf", async () => {
    const nep = nepUpstream();
    vi.stubGlobal("fetch", nep);

    await POST(verzoek(""), params);

    expect(nep.mock.calls[0][0]).toContain("formaat=pdf");
  });
});
