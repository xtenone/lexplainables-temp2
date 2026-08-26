// Weergave-helpers voor het act-3-schema: begrippen als bouwstenen van afleidingsregels.
// Gedeeld door ReviewPanel en RapportView zodat de begrip-graaf op beide plekken
// hetzelfde leest (id → naam, herkomst-label, regel-velden als begripnamen).

import type {
  Afleidingsregel, Begrip, BegripHerkomst, BegripRelatie, RegelParameter, RegelVoorwaarde,
} from "./types";

/** begrip-id → voorkeursterm, voor het tonen van referenties als namen. */
export function begripNaamMap(begrippen: Begrip[] | undefined): Record<string, string> {
  const map: Record<string, string> = {};
  for (const b of begrippen ?? []) map[b.id] = b.naam || b.id;
  return map;
}

/** Toon een begrip-referentie als "naam (id)" — het id blijft zichtbaar voor de feedback-lus. */
export function begripRef(id: string | undefined | null, namen: Record<string, string>): string {
  if (!id) return "";
  const naam = namen[id];
  return naam && naam !== id ? `${naam} (${id})` : id;
}

export function invoerText(
  invoer: { begrip_id: string; toelichting?: string }[] | undefined,
  namen: Record<string, string>,
): string {
  return (invoer ?? [])
    .map((i) => begripRef(i.begrip_id, namen) + (i.toelichting ? ` — ${i.toelichting}` : ""))
    .join("; ");
}

export function parameterText(p: RegelParameter, namen: Record<string, string>): string {
  const delen = [begripRef(p.begrip_id, namen)];
  if (p.waarde) {
    delen.push(`= ${p.waarde}${p.eenheid ? ` ${p.eenheid}` : ""}`);
  } else {
    delen.push("(waarde in delegatie)");
  }
  if (p.geldigheid) delen.push(`[${p.geldigheid}]`);
  if (p.toelichting) delen.push(`— ${p.toelichting}`);
  return delen.join(" ");
}

export function parametersText(
  parameters: RegelParameter[] | undefined,
  namen: Record<string, string>,
): string {
  return (parameters ?? []).map((p) => parameterText(p, namen)).join("; ");
}

/** Voorwaarden als leesbare keten: "indien X · EN indien Y". */
export function voorwaardenText(
  voorwaarden: RegelVoorwaarde[] | undefined,
  namen: Record<string, string>,
): string {
  return (voorwaarden ?? [])
    .map((v, i) => {
      const prefix = i > 0 && v.verbinding ? `${v.verbinding} ` : "";
      const ids = (v.begrip_ids ?? []).map((id) => begripRef(id, namen)).join(", ");
      return prefix + v.tekst + (ids ? ` [${ids}]` : "");
    })
    .join(" · ");
}

export function relatiesText(
  relaties: BegripRelatie[] | undefined,
  namen: Record<string, string>,
): string {
  return (relaties ?? [])
    .map((r) => {
      const doel = r.doel_begrip ? ` → ${begripRef(r.doel_begrip, namen)}` : "";
      return `${r.soort ? `${r.soort}: ` : ""}${r.beschrijving}${doel}`;
    })
    .join("; ");
}

export function verwijstNaarText(
  ids: string[] | undefined,
  namen: Record<string, string>,
): string {
  return (ids ?? []).map((id) => begripRef(id, namen)).join(", ");
}

/** Kort herkomst-label voor een badge/veld: "hergebruikt (ab1)", "aangepast (ab2)", "nieuw". */
export function herkomstLabel(h: BegripHerkomst | null | undefined): string {
  if (!h?.status) return "";
  return h.aangeleverd_id ? `${h.status} (${h.aangeleverd_id})` : h.status;
}

/** Alle regel-velden van een afleidingsregel als (label, waarde)-paren met begripnamen. */
export function regelVelden(
  r: Afleidingsregel,
  namen: Record<string, string>,
): { label: string; waarde: string }[] {
  const uitvoer = r.uitvoer?.begrip_id
    ? begripRef(r.uitvoer.begrip_id, namen)
      + (r.uitvoer.toelichting ? ` — ${r.uitvoer.toelichting}` : "")
    : "";
  return [
    { label: "Uitvoer", waarde: uitvoer },
    { label: "Invoer", waarde: invoerText(r.invoer, namen) },
    { label: "Parameters", waarde: parametersText(r.parameters, namen) },
    { label: "Voorwaarden", waarde: voorwaardenText(r.voorwaarden, namen) },
    { label: "Toelichting", waarde: r.toelichting ?? "" },
  ];
}
