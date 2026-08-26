// BFF-route voor het starten en opzoeken van een agent-run (graph-qa /v1/runs).
//
// Waarom naast de bestaande agent-route: die koppelt de beurt aan de verbinding van één tabblad —
// wegklikken of herladen doodde het antwoord. Een run is een object van de server; starten,
// meekijken (`[id]/events`) en stoppen (`[id]/cancel`) zijn losse handelingen.

import { proxy } from "@/app/api/_lib/proxy";
import { graphQaAuthHeader, graphQaBaseUrl } from "@/lib/config";
import { logger } from "@/lib/logger";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

// Starten is een korte call: de agent zet een achtergrondtaak weg en antwoordt meteen. Het lange
// wachten gebeurt op de events-route, niet hier.
const START_TIMEOUT_MS = 15_000;

export async function POST(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();

  // De identiteit gaat als HEADER mee, niet in de body — één mechanisme voor alle run-routes en
  // hetzelfde als de api hanteert. Ze kwam eerder in de body, en toen liepen de twee bronnen bij de
  // eerste eigenaarscontrole meteen uit elkaar.
  const body = await req.text();
  let gesprekId = "";
  try {
    const ontleed = JSON.parse(body) as Record<string, unknown>;
    gesprekId = typeof ontleed.conversation_id === "string" ? ontleed.conversation_id : "";
  } catch {
    // Geen geldige JSON: laat de agent er zelf een 422 van maken in plaats van hier te raden.
  }

  // Is dit gesprek wel van jou? `conversation_id` is óók de thread_id van het agent-geheugen, dus
  // zonder deze controle kan iemand met een vreemd gespreks-id een vraag in andermans geheugen
  // injecteren en de context daarvan teruglezen. De api is de eigenaarsadministratie; die vragen we.
  if (gesprekId) {
    const eigen = await proxy(`/v1/gesprekken/${pathSegment(gesprekId)}`, {
      headers: { "X-User-Id": userid },
    });
    if (!eigen.ok) {
      return Response.json({ detail: "Onbekend gesprek." }, { status: 404 });
    }
  }

  try {
    // Bewust ZONDER `req.signal`: de browser die deze POST afbreekt mag de run niet meenemen —
    // dat was precies de oude fout. Alleen een eigen timeout op het starten zelf.
    const upstream = await fetch(`${graphQaBaseUrl()}/v1/runs`, {
      method: "POST",
      headers: { ...graphQaAuthHeader(), "X-User-Id": userid, "Content-Type": "application/json" },
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(START_TIMEOUT_MS),
    });
    const text = await upstream.text();
    // 409 (er loopt al een run) gaat ongewijzigd door: de client hoort daarop aan te haken bij het
    // meegegeven run_id, niet te falen.
    return new Response(text || null, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    logger.warn("Run-proxy: agent onbereikbaar", { fout: (err as Error).message });
    return Response.json({ detail: `Agent onbereikbaar (${(err as Error).message})` }, { status: 502 });
  }
}

/** `?gesprek=<id>` → de run waar je op kunt aanhaken, of `null`. Dit is wat de werkplek bij
 *  binnenkomst vraagt om een lopende beurt weer in beeld te krijgen. */
export async function GET(req: Request) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();

  const gesprek = new URL(req.url).searchParams.get("gesprek") ?? "";
  if (!gesprek) return Response.json(null);
  try {
    const upstream = await fetch(
      `${graphQaBaseUrl()}/v1/conversations/${encodeURIComponent(gesprek)}/run`,
      {
        // Zonder deze header zou een gespreks-id — dat gewoon in de URL van de werkplek staat —
        // genoeg zijn om andermans lopende vraag en antwoord te lezen.
        headers: { ...graphQaAuthHeader(), "X-User-Id": userid },
        cache: "no-store",
        signal: AbortSignal.timeout(10_000),
      },
    );
    const text = await upstream.text();
    return new Response(text || null, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/json" },
    });
  } catch (err) {
    // Een fout is géén `null`: `null` betekent "er loopt niets", en dat is een uitspraak die we hier
    // juist niet kunnen doen. Gaven we hem toch, dan las de werkplek een timeout als een beurt die
    // verdwenen was — mét de bijbehorende waarschuwing — terwijl de run gewoon doorliep. De client
    // maakt dat onderscheid wél (`haalActieveRun` → `"onbekend"`) en laat het dan stil.
    logger.warn("Run-proxy: actieve run niet op te halen", { fout: (err as Error).message });
    return Response.json({ detail: "Actieve run niet op te halen." }, { status: 502 });
  }
}
