// Bouw precies één URL-pad-segment uit een (mogelijk al ge-encode) waarde.
//
// Next.js (App Router) levert dynamische route-params URL-geëncodeerd aan. Zo'n param dan
// nóg eens met encodeURIComponent in een upstream-URL coderen verdubbelt gereserveerde
// tekens: een artikelnummer als 4:86 wordt in de slug `...-art4:86`, de ':' wordt door de
// browser/Next `%3A`, en een tweede encode maakt daar `%253A` van — waarop de upstream-lookup
// 404't ("Project niet gevonden"). Eerst decoderen en dan precies één keer encoderen maakt de
// bewerking idempotent: zowel een al-geëncode als een kale waarde levert één, correct
// geëncodeerd segment op.
export function pathSegment(value: string): string {
  let decoded = value;
  try {
    decoded = decodeURIComponent(value);
  } catch {
    // Geen geldige percent-encoding: behandel de waarde als reeds gedecodeerd.
  }
  return encodeURIComponent(decoded);
}

// wetten.overheid.nl heeft voor een jci-deeplink zowel de zichtdatum (`&z=`) als de
// geldigheidsdatum (`&g=`) nodig; een jci met alléén `&g=` landt bovenaan de wet i.p.v. op de
// bepaling. De MCP levert nu alleen `&g=<datum>`, dus vul `&z=<zelfde datum>` aan als die ontbreekt
// (conform het format dat wetten.overheid.nl in zijn eigen bron-XML gebruikt: `…&z=D&g=D`). Een jci
// zónder datum (kale kruisverwijzing) laten we ongemoeid — die resolvet naar de actuele versie.
export function normaliseerJci(jci: string): string {
  const g = jci.match(/[?&]g=(\d{4}-\d{2}-\d{2})/);
  if (g && !/[?&]z=/.test(jci)) {
    return jci.replace(/([?&])g=/, `$1z=${g[1]}&g=`);
  }
  return jci;
}

// Veilige href voor een bronreferentie. Het veld komt (indirect) uit de analyse-pipeline/LLM
// en mag dus niet blind in een href: een waarde als `javascript:…` zou klikbare
// scriptuitvoering opleveren (React escaped tekst, maar niet de href-scheme).
//   - jci-uri (`jci1.3:c:BWBR…`)  → deeplink op wetten.overheid.nl (repareert meteen het
//     anders niet-navigeerbare jci-linkje);
//   - al complete http(s)-URL     → alleen toegestaan als de host wetten.overheid.nl is (host-pinning,
//     net als wettenOverheidHref) — een vreemde host wordt platte tekst, geen phishing-link;
//   - alles anders (javascript:, data:, leeg) → undefined ⇒ render als platte tekst, geen <a>.
export function bronHref(ref?: string | null): string | undefined {
  if (!ref) return undefined;
  const trimmed = ref.trim();
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      return new URL(trimmed).hostname === "wetten.overheid.nl" ? trimmed : undefined;
    } catch {
      return undefined;
    }
  }
  if (/^jci/i.test(trimmed)) return `https://wetten.overheid.nl/${encodeURI(normaliseerJci(trimmed))}`;
  return undefined;
}

// Gebruik alleen het pad van een callbackUrl op hetzelfde origin; voorkomt een sprong naar een
// andere host (bv. een intern 0.0.0.0:3000 dat door een verkeerd geconfigureerde proxy ontstaat).
// `origin` is een parameter i.p.v. een greep naar `window.location.origin`, zodat de functie ook
// buiten de browser te testen is. Gebruikt na het inloggen én na het accepteren van de disclaimer.
export function veiligPad(cb: string | null, origin: string): string {
  if (!cb) return "/";
  try {
    const u = new URL(cb, origin);
    return u.origin === origin ? u.pathname + u.search : "/";
  } catch {
    // Alleen een echt intern pad; sluit protocol-relatieve paden (`//evil.com`) expliciet uit.
    return cb.startsWith("/") && !cb.startsWith("//") ? cb : "/";
  }
}

// Veilige href voor een verwijzing-target: altijd als pad ónder wetten.overheid.nl opgebouwd,
// en daarna gevalideerd, zodat een vreemd schema of een andere host nooit kan ontsnappen.
export function wettenOverheidHref(target?: string | null): string | undefined {
  if (!target) return undefined;
  const url = `https://wetten.overheid.nl/${encodeURI(normaliseerJci(target.trim()))}`;
  try {
    return new URL(url).hostname === "wetten.overheid.nl" ? url : undefined;
  } catch {
    return undefined;
  }
}
