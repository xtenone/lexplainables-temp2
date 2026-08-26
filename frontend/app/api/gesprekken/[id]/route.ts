import { proxy } from "@/app/api/_lib/proxy";
import { geenSessie, sessionUserId } from "@/app/api/_lib/session";
import { graphQaAuthHeader, graphQaBaseUrl } from "@/lib/config";
import { logger } from "@/lib/logger";
import { pathSegment } from "@/lib/url";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

/** Stop de lopende beurt en wis het agent-geheugen (graph-qa checkpointer-thread) van dit gesprek.
 *  Best-effort: een falen mag de UI-delete niet blokkeren — de checkpointer-thread ruimt anders later
 *  op (of blijft hooguit ongebruikt staan). */
async function wisAgentGeheugen(id: string, userid: string): Promise<void> {
  try {
    await fetch(`${graphQaBaseUrl()}/v1/conversations/${pathSegment(id)}`, {
      method: "DELETE",
      // De identiteit gaat mee, net als op de run-routes: deze delete stopt ook een lopende beurt,
      // en graph-qa weigert dat voor een run van iemand anders. De api heeft het eigenaarschap dan
      // al vastgesteld — dit is het tweede net, niet het eerste.
      headers: { ...graphQaAuthHeader(), "X-User-Id": userid },
      cache: "no-store",
    });
  } catch (err) {
    logger.warn("Agent-geheugen wissen mislukt", { fout: (err as Error).message });
  }
}

export async function GET(_req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { id } = await params;
  return proxy(`/v1/gesprekken/${pathSegment(id)}`, { headers: { "X-User-Id": userid } });
}

export async function PATCH(req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { id } = await params;
  return proxy(`/v1/gesprekken/${pathSegment(id)}`, {
    method: "PATCH",
    body: await req.text(),
    headers: { "X-User-Id": userid, "Content-Type": "application/json" },
  });
}

export async function DELETE(_req: Request, { params }: Params) {
  const userid = await sessionUserId();
  if (!userid) return geenSessie();
  const { id } = await params;
  // Eigenaarschap eerst laten vaststellen door de api, zonder al te verwijderen: pas als dit
  // gesprek van jou is, mag de lopende beurt gestopt worden.
  const eigen = await proxy(`/v1/gesprekken/${pathSegment(id)}`, { headers: { "X-User-Id": userid } });
  // Stoppen vóór verwijderen: andersom bleef er een venster waarin de agent doorwerkte en aan het
  // eind in een gesprek schreef dat al weg was.
  if (eigen.ok) await wisAgentGeheugen(id, userid);
  return proxy(`/v1/gesprekken/${pathSegment(id)}`, {
    method: "DELETE",
    headers: { "X-User-Id": userid },
  });
}
