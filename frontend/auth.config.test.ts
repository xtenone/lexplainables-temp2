// Tests voor de authorized-callback: de CSRF Origin-check (defense-in-depth naast
// SameSite=Lax) op muterende BFF-routes en de PoC-disclaimer-gate, zonder de rol-/sessie-gates
// te breken.

import { describe, expect, it } from "vitest";
import { authConfig } from "./auth.config";
import { DISCLAIMER_COOKIE } from "./lib/disclaimer";

type AuthorizedFn = (params: { auth: unknown; request: unknown }) => unknown;
const authorized = authConfig.callbacks.authorized as unknown as AuthorizedFn;

// De disclaimer-gate leest `request.cookies`; standaard doen we alsóf het akkoord er al is, zodat
// de Origin-tests hieronder blijven testen wat ze testen. `akkoord: false` zet de gate aan.
function fakeRequest(
  method: string,
  url: string,
  headers: Record<string, string> = {},
  akkoord = true,
) {
  return {
    method,
    nextUrl: new URL(url),
    headers: new Headers(headers),
    cookies: {
      get: (naam: string) =>
        akkoord && naam === DISCLAIMER_COOKIE ? { name: naam, value: "1" } : undefined,
    },
  };
}

const sessie = { user: { userid: "an1", role: "analist" } };

describe("Origin-check op muterende BFF-routes", () => {
  it("weigert een POST met een vreemde Origin (403)", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("POST", "https://app.example/api/projects", {
        origin: "https://evil.example",
      }),
    });
    expect(res).toBeInstanceOf(Response);
    expect((res as Response).status).toBe(403);
  });

  it("laat een POST met de eigen Origin door", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("POST", "https://app.example/api/projects", {
        origin: "https://app.example",
      }),
    });
    expect(res).toBe(true);
  });

  it("accepteert de x-forwarded-host achter de proxy", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("POST", "http://intern:3000/api/projects", {
        origin: "https://app.example",
        "x-forwarded-host": "app.example",
      }),
    });
    expect(res).toBe(true);
  });

  it("weigert een onparseerbare Origin (403)", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("POST", "https://app.example/api/projects", {
        origin: "geen-geldige-url",
      }),
    });
    expect(res).toBeInstanceOf(Response);
    expect((res as Response).status).toBe(403);
  });

  it("valt zonder Origin-header terug op SameSite (geen 403)", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("POST", "https://app.example/api/projects"),
    });
    expect(res).toBe(true);
  });

  it("laat GET met vreemde Origin ongemoeid (alleen muterende methodes)", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/api/projects", {
        origin: "https://evil.example",
      }),
    });
    expect(res).toBe(true);
  });

  it("geldt óók op publieke routes zoals /api/login-verify", async () => {
    const res = await authorized({
      auth: null,
      request: fakeRequest("POST", "https://app.example/api/login-verify", {
        origin: "https://evil.example",
      }),
    });
    expect(res).toBeInstanceOf(Response);
    expect((res as Response).status).toBe(403);
  });

  it("blijft zonder sessie gewoon weigeren (rol-/sessie-gate intact)", async () => {
    const res = await authorized({
      auth: null,
      request: fakeRequest("POST", "https://app.example/api/projects", {
        origin: "https://app.example",
      }),
    });
    expect(res).toBe(false);
  });
});

describe("PoC-disclaimer-gate", () => {
  it("stuurt een ingelogde gebruiker zonder akkoord naar /disclaimer", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/", {}, false),
    });
    expect(new URL((res as Response).headers.get("location")!).pathname).toBe("/disclaimer");
  });

  it("draagt de oorspronkelijke bestemming mee als callbackUrl", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/projecten/abc?tab=rapport", {}, false),
    });
    const doel = new URL((res as Response).headers.get("location")!);
    expect(doel.searchParams.get("callbackUrl")).toBe("/projecten/abc?tab=rapport");
  });

  it("laat door zodra het akkoord er is", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/"),
    });
    expect(res).toBe(true);
  });

  it("gate't de BFF-routes niet (anders breken de SSE-streams)", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/api/projects/events", {}, false),
    });
    expect(res).toBe(true);
  });

  it("stuurt /disclaimer niet naar zichzelf door", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/disclaimer", {}, false),
    });
    expect(res).toBe(true);
  });

  it("houdt /login bereikbaar zonder akkoord", async () => {
    const res = await authorized({
      auth: null,
      request: fakeRequest("GET", "https://app.example/login", {}, false),
    });
    expect(res).toBe(true);
  });

  it("houdt /disclaimer zelf bereikbaar zonder sessie (moet ook zonder inloggen na te lezen zijn)", async () => {
    const res = await authorized({
      auth: null,
      request: fakeRequest("GET", "https://app.example/disclaimer", {}, false),
    });
    expect(res).toBe(true);
  });

  it("gaat vóór de rolgate: een analist op /beheer ziet eerst de disclaimer", async () => {
    const res = await authorized({
      auth: sessie,
      request: fakeRequest("GET", "https://app.example/beheer", {}, false),
    });
    expect(new URL((res as Response).headers.get("location")!).pathname).toBe("/disclaimer");
  });
});
