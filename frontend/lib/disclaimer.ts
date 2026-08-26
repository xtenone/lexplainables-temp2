// Gedeelde constanten voor de PoC-disclaimer. Bewust een eigen module ZONDER `server-only`:
// zowel de edge-routegate (`auth.config.ts`) als de server-only cookiehelpers
// (`lib/authCookies.ts`) hebben de cookienaam nodig, en `lib/authCookies.ts` is vanuit de edge
// niet importeerbaar (die leest `next/headers`). Eén bron van waarheid voor de naam dus hier.
//
// De cookie draagt geen waarde van betekenis — alleen zijn aanwezigheid telt ("akkoord gezien").
// Hij wordt bewust ZONDER maxAge gezet (sessiecookie): bij elke nieuwe browsersessie/login komt de
// disclaimer terug. Bij een proefopstelling waar analyses kunnen verdwijnen moet die waarschuwing
// scherp blijven.

// Naamprefix spiegelt lib/authCookies.ts: `__Secure-` vereist `secure: true`, dus naam en vlag
// bewegen samen met dezelfde NODE_ENV-check (Next inlinet die op buildtijd, ook in de edge-bundel).
export const DISCLAIMER_COOKIE =
  process.env.NODE_ENV === "production" ? "__Secure-wa-disclaimer" : "wa-disclaimer";

export const DISCLAIMER_PAD = "/disclaimer";

/** Moet dit pad achter het disclaimer-akkoord staan?
 *
 *  Twee vrijstellingen, allebei noodzakelijk:
 *  - `/api/**` — de BFF-routes en vooral de SSE-streams (`/api/projects/events`). Een redirect naar
 *    een HTML-pagina breekt daar de stream met een parsefout in plaats van een nette 401/403.
 *  - `/disclaimer` zelf — anders stuurt de gate de pagina naar zichzelf door (redirect-lus). */
export function vereistAkkoord(path: string): boolean {
  if (path.startsWith("/api/")) return false;
  return path !== DISCLAIMER_PAD;
}
