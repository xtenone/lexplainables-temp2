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

// De basis van de IRI's in de kennisgraaf (`GRAPHDB_BASE_IRI` in de bwb-importer). Vindplaatsen uit
// de tool-trace kunnen in die vorm binnenkomen; ze zijn intern en dus niet publiek te openen.
// Bewaakt door tools/graph-qa/tests/test_namespace_drift.py — deze constante is de enige koppeling
// met de importer, want client-side code kan de env niet lezen.
const GRAAF_BASIS = "urn:bwb:";
// Segmentscheiding: `:` in de URN-ruimte, `/` als de basis ooit weer een http-IRI wordt.
const GRAAF_SEP = GRAAF_BASIS.startsWith("urn:") ? ":" : "/";
const BWB_ID = /^BWBR\d+$/;

// Een graaf-IRI naar de publieke vindplaats vertalen. De IRI is systematisch opgebouwd uit
// sleutel/waarde-paren achter het BWB-id (`urn:bwb:BWBR0004770:artikel:2:lid:1`), dus de omzetting
// naar een jci is mechanisch — de spiegel van `Vocab.canonieke_url` in de importer.
//
// Niet elke IRI hééft een publieke vorm: `:id:…` (niet-citeerbare knoop), `:ref:…` (gehashte
// terugval), `:begrip:…`, `:graph:…` en `:verwijzing:…` bestaan alleen in de graaf. Daar is geen link
// beter dan een link die ergens anders uitkomt.
function uitGraafIri(iri: string): string | undefined {
  const pad = iri.slice(GRAAF_BASIS.length).split(GRAAF_SEP).filter(Boolean).map(decodeURIComponent);
  const [bwb, ...rest] = pad;
  if (!bwb || !BWB_ID.test(bwb)) return undefined;
  if (rest.length === 0) return `https://wetten.overheid.nl/${bwb}`;
  // De rest zijn sleutel/waarde-paren; een oneven staart of een lege waarde betekent: niet te citeren.
  if (rest.length % 2 !== 0) return undefined;
  const delen: string[] = [];
  for (let i = 0; i < rest.length; i += 2) {
    const sleutel = rest[i];
    const waarde = rest[i + 1];
    if (!sleutel || !waarde || sleutel === "id") return undefined;
    delen.push(`&${encodeURIComponent(sleutel)}=${encodeURIComponent(waarde)}`);
  }
  return `https://wetten.overheid.nl/jci1.3:c:${bwb}${delen.join("")}`;
}

// Veilige href voor een vindplaats. Het veld komt (indirect) uit de graaf/LLM en mag dus niet blind
// in een href: een waarde als `javascript:…` zou klikbare scriptuitvoering opleveren (React escaped
// tekst, maar niet de href-scheme). Eén functie voor álle vormen die de agent kan leveren, want twee
// helpers met bijna dezelfde naam leverden precies één verkeerde keuze op: de bronnenlijst bouwde
// `https://wetten.overheid.nl/<graaf-IRI>` en dat kwam door de hostcontrole heen. De URN-tak is
// bewust gepind op `urn:bwb:` en niet op `urn:` in het algemeen: een willekeurige URN is geen
// vindplaats en mag hier niets worden.
//   - jci-uri (`jci1.3:c:BWBR…`)  → deeplink op wetten.overheid.nl (repareert meteen het
//     anders niet-navigeerbare jci-linkje);
//   - graaf-IRI (`urn:bwb:…`) → vertaald naar diezelfde deeplink, of undefined als de
//     knoop geen publieke vindplaats heeft;
//   - kaal BWB-id (`BWBR0004770`)  → de regelingpagina;
//   - al complete http(s)-URL     → alleen toegestaan als de host wetten.overheid.nl is (host-pinning) —
//     een vreemde host wordt platte tekst, geen phishing-link;
//   - alles anders (javascript:, data:, leeg) → undefined ⇒ render als platte tekst, geen <a>.
export function bronHref(ref?: string | null): string | undefined {
  if (!ref) return undefined;
  const trimmed = ref.trim();
  if (trimmed.startsWith(GRAAF_BASIS)) return uitGraafIri(trimmed);
  if (/^https?:\/\//i.test(trimmed)) {
    try {
      return new URL(trimmed).hostname === "wetten.overheid.nl" ? trimmed : undefined;
    } catch {
      return undefined;
    }
  }
  if (/^jci/i.test(trimmed)) return `https://wetten.overheid.nl/${encodeURI(normaliseerJci(trimmed))}`;
  if (BWB_ID.test(trimmed)) return `https://wetten.overheid.nl/${trimmed}`;
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
