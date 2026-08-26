"use client";

import { Card, Section } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { JasBadge, Tag } from "@/components/ui/Badge";
import { LedenLijst } from "@/components/LedenLijst";
import { bronHref, wettenOverheidHref } from "@/lib/url";
import {
  begripNaamMap, herkomstLabel, regelVelden, relatiesText, verwijstNaarText,
} from "@/lib/begrippen";
import { bronLabel, bronLabelMap, vindplaatsText } from "@/lib/bronnen";
import { jasVolgorde } from "@/lib/jas";
import type { Bron, Markering, Rapport, Verwijzing } from "@/lib/types";

const VERWIJZING_FUNCTIE_LABEL: Record<string, string> = {
  definitie: "Definitie",
  schakel: "Schakel / afwijking",
  delegatie: "Delegatie",
  "intra-artikel": "Intra-artikel",
  informatief: "Informatief",
};
const VERWIJZING_FUNCTIE_VOLGORDE = ["definitie", "schakel", "delegatie", "intra-artikel", "informatief"];
const VERWIJZING_STATUS_LABEL: Record<string, string> = {
  opgehaald: "opgehaald",
  gevolgd: "gevolgd",
  gesignaleerd: "gesignaleerd",
  "buiten-scope-diepte": "buiten scope",
};

function Twijfel({ tekst }: { tekst?: string }) {
  if (!tekst) return null;
  return (
    <Melding type="waarschuwing" compact className="mt-2 text-xs">
      Twijfel: {tekst}
    </Melding>
  );
}

function Veld({ label, waarde }: { label: string; waarde?: string }) {
  if (!waarde) return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-28 shrink-0 text-xs uppercase tracking-wide text-faint">{label}</span>
      <span className="min-w-0 break-words text-muted">{waarde}</span>
    </div>
  );
}

/** Eén bron in het werkgebied: wettekst, markeringen (per JAS-klasse), verwijzingen, samenhang. */
function BronSectie({ bron }: { bron: Bron }) {
  const markeringenPerKlasse = groepeer(bron.markeringen ?? []);
  return (
    <Section title={bronLabel(bron)} subtitle={bron.bwbId} level={3}>
      <div className="space-y-6">
        <div className="flex flex-wrap gap-2">
          {bron.versiedatum && <Tag>versie {bron.versiedatum}</Tag>}
          {bronHref(bron.bronreferentie) ? (
            <a
              href={bronHref(bron.bronreferentie)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center rounded-md border border-line bg-paper px-2 py-0.5 font-mono text-xs text-link hover:underline"
            >
              bron ↗
            </a>
          ) : null}
        </div>

        {bron.leden?.length > 0 && <LedenLijst leden={bron.leden} />}

        {bron.markeringen?.length > 0 && (
          <div className="space-y-6">
            {markeringenPerKlasse.map(([klasse, items]) => (
              <div key={klasse}>
                <div className="mb-2 flex items-center gap-2">
                  <JasBadge klasse={klasse} />
                  <span className="font-mono text-xs text-faint">{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((m) => (
                    <Card key={m.id} className="p-4">
                      <p className="break-words font-display text-[15px] leading-relaxed text-ink">
                        “{m.formulering}”
                      </p>
                      <div className="mt-2 space-y-1">
                        <Veld label="Vindplaats" waarde={m.vindplaats} />
                        <Veld label="Toelichting" waarde={m.toelichting} />
                      </div>
                      <Twijfel tekst={m.twijfel} />
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {bron.verwijzingen?.length > 0 && (
          <div className="space-y-6">
            <p className="text-xs uppercase tracking-wide text-faint">Verwijzingen (uitgaand)</p>
            {groepeerVerwijzingen(bron.verwijzingen).map(([functie, items]) => (
              <div key={functie}>
                <div className="mb-2 flex items-center gap-2">
                  <Tag>{VERWIJZING_FUNCTIE_LABEL[functie] ?? functie}</Tag>
                  <span className="font-mono text-xs text-faint">{items.length}</span>
                </div>
                <div className="space-y-2">
                  {items.map((v) => (
                    <Card key={v.id} className="p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        {v.doel?.target && wettenOverheidHref(v.doel.target) ? (
                          <a
                            href={wettenOverheidHref(v.doel.target)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="min-w-0 break-words font-display text-[15px] text-link hover:underline"
                          >
                            {v.doel.label || v.doel.target} ↗
                          </a>
                        ) : (
                          <span className="min-w-0 break-words font-display text-[15px] text-ink">
                            {v.doel?.label || v.doel?.target || "(verwijzing)"}
                          </span>
                        )}
                        <Tag>{VERWIJZING_STATUS_LABEL[v.status] ?? v.status}</Tag>
                        {v.soort && (
                          <span className="font-mono text-xs text-faint">
                            {v.soort}
                            {v.doel?.bwbId && bron.bwbId && v.doel.bwbId !== bron.bwbId ? " · extern" : ""}
                          </span>
                        )}
                        {v.bron_lid && <span className="font-mono text-xs text-faint">{v.bron_lid}</span>}
                      </div>
                      {v.betekenis && (
                        <p className="mt-2 text-sm leading-relaxed text-muted">{v.betekenis}</p>
                      )}
                    </Card>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {bron.samenhang && (
          <Card className="p-4">
            <p className="text-xs uppercase tracking-wide text-faint">Samenhang</p>
            <p className="mt-1 text-sm leading-relaxed text-muted">{bron.samenhang}</p>
          </Card>
        )}
      </div>
    </Section>
  );
}

export function RapportView({ rapport }: { rapport: Rapport }) {
  const wg = rapport.werkgebied ?? ({} as Rapport["werkgebied"]);
  const bronnen = rapport.bronnen ?? [];
  const labels = bronLabelMap(bronnen);
  const namen = begripNaamMap(rapport.begrippen);
  const hoofdvraag = wg.hoofdvraag || wg.analysefocus;

  return (
    <div className="space-y-10">
      {/* Kop — werkgebied (fase-kop: h2) */}
      <Card className="p-6">
        <h2 className="font-display text-xl font-semibold text-lint">{wg.naam || "Wetsanalyse"}</h2>
        <p className="mt-1 text-sm text-muted">
          Werkgebied · {bronnen.length} bron{bronnen.length === 1 ? "" : "nen"}
        </p>
        {(hoofdvraag || wg.omschrijving || wg.scoping) && (
          <div className="mt-4 space-y-1.5 border-t border-line pt-4">
            <Veld label="Hoofdvraag" waarde={hoofdvraag} />
            <Veld label="Omschrijving" waarde={wg.omschrijving} />
            <Veld label="Afbakening" waarde={wg.scoping} />
          </div>
        )}
        {bronnen.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-line pt-4">
            {bronnen.map((b) => (
              <Tag key={b.bron_id}>{bronLabel(b)}</Tag>
            ))}
          </div>
        )}
      </Card>

      {/* Per bron: wettekst, markeringen, verwijzingen, samenhang */}
      {bronnen.map((b) => (
        <BronSectie key={b.bron_id} bron={b} />
      ))}

      {/* Begrippen — gedeeld over het werkgebied */}
      {rapport.begrippen?.length > 0 && (
        <Section title="Begrippen" count={rapport.begrippen.length} subtitle="activiteit 3 · gedeeld" level={3}>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {[...rapport.begrippen].sort((a, b) => jasVolgorde(a.klasse) - jasVolgorde(b.klasse)).map((b) => (
              <Card key={b.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 break-words font-display text-base font-medium text-ink">{b.naam}</p>
                  <div className="flex shrink-0 flex-wrap justify-end gap-1">
                    {b.herkomst?.status && <Tag>{herkomstLabel(b.herkomst)}</Tag>}
                    {b.klasse && <JasBadge klasse={b.klasse} />}
                  </div>
                </div>
                <div className="mt-2 space-y-1">
                  {b.synoniemen?.length > 0 && <Veld label="Synoniemen" waarde={b.synoniemen.join(", ")} />}
                  <Veld
                    label="Definitie"
                    waarde={b.definitie ? b.definitie + (b.is_interpretatie ? " [interpretatie]" : "") : ""}
                  />
                  <Veld label="Grondformulering" waarde={b.grondformulering} />
                  <Veld label="Voorbeeld" waarde={b.voorbeeld} />
                  <Veld label="Kenmerken" waarde={b.kenmerken} />
                  <Veld label="Relaties" waarde={relatiesText(b.relaties, namen)} />
                  <Veld label="Verwijst naar" waarde={verwijstNaarText(b.verwijst_naar_begrippen, namen)} />
                  <Veld label="Bron-verwijzing" waarde={b.bron_verwijzing} />
                  <Veld
                    label="Herkomst"
                    waarde={b.herkomst?.motivatie ? `${herkomstLabel(b.herkomst)} — ${b.herkomst.motivatie}` : ""}
                  />
                  <Veld label="Vindplaats" waarde={vindplaatsText(b.vindplaatsen, labels)} />
                </div>
                <Twijfel tekst={b.twijfel} />
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* Afleidingsregels — gedeeld over het werkgebied */}
      {rapport.afleidingsregels?.length > 0 && (
        <Section title="Afleidingsregels" count={rapport.afleidingsregels.length} subtitle="activiteit 3 · gedeeld" level={3}>
          <div className="space-y-3">
            {rapport.afleidingsregels.map((r) => (
              <Card key={r.id} className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 break-words font-display text-base font-medium text-ink">{r.naam}</p>
                  {r.type && <Tag>{r.type}</Tag>}
                </div>
                <div className="mt-2 space-y-1">
                  {regelVelden(r, namen).map((v) => (
                    <Veld key={v.label} label={v.label} waarde={v.waarde} />
                  ))}
                  <Veld label="Vindplaats" waarde={vindplaatsText(r.vindplaatsen, labels)} />
                </div>
                <Twijfel tekst={r.twijfel} />
              </Card>
            ))}
          </div>
        </Section>
      )}

      {/* Validatiepunten */}
      {rapport.validatiepunten?.length > 0 && (
        <Section title="Validatiepunten" count={rapport.validatiepunten.length} level={3}>
          <Card className="p-4">
            <ul className="list-inside list-disc space-y-1 text-sm text-muted">
              {rapport.validatiepunten.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
          </Card>
        </Section>
      )}

      {/* Reviewlog */}
      <Reviewlog rapport={rapport} />

      {/* Aandachtspunten */}
      {rapport.aandachtspunten && (
        <Section title="Aandachtspunten" level={3}>
          <Card className="p-4">
            <p className="whitespace-pre-line text-sm leading-relaxed text-muted">
              {rapport.aandachtspunten}
            </p>
          </Card>
        </Section>
      )}
    </div>
  );
}

function groepeer(markeringen: Markering[]): [string, Markering[]][] {
  const map = new Map<string, Markering[]>();
  for (const m of markeringen) {
    const k = m.klasse || "Overig";
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(m);
  }
  return [...map.entries()].sort((a, b) => jasVolgorde(a[0]) - jasVolgorde(b[0]));
}

function groepeerVerwijzingen(verwijzingen: Verwijzing[]): [string, Verwijzing[]][] {
  const map = new Map<string, Verwijzing[]>();
  for (const v of verwijzingen) {
    const k = v.functie || "informatief";
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(v);
  }
  return [...map.entries()].sort(
    (a, b) => VERWIJZING_FUNCTIE_VOLGORDE.indexOf(a[0]) - VERWIJZING_FUNCTIE_VOLGORDE.indexOf(b[0]),
  );
}

function Reviewlog({ rapport }: { rapport: Rapport }) {
  const log = rapport.reviewlog ?? {};
  const blokken = (["activiteit2", "activiteit3"] as const)
    .map((k) => ({ key: k, data: log[k] }))
    .filter((b) => b.data && (b.data.samenvatting || (b.data.rondes?.length ?? 0) > 0));
  if (blokken.length === 0) return null;

  return (
    <Section title="Reviewlog" level={3}>
      <div className="space-y-3">
        {blokken.map(({ key, data }) => (
          <details key={key} className="rounded-xl border border-line bg-surface/80 p-4">
            <summary className="cursor-pointer text-sm font-medium text-ink">
              {key === "activiteit2" ? "Activiteit 2" : "Activiteit 3"}
              {data?.rondes?.length ? (
                <span className="ml-2 font-mono text-xs text-faint">
                  {data.rondes.length} ronde(n)
                </span>
              ) : null}
            </summary>
            {data?.samenvatting && <p className="mt-2 text-sm text-muted">{data.samenvatting}</p>}
            <div className="mt-3 space-y-2">
              {data?.rondes?.map((r) => (
                <div key={r.ronde} className="rounded border border-line/60 bg-paper/50 p-3 text-sm">
                  <p className="font-mono text-xs text-faint">ronde {r.ronde}</p>
                  {r.algemeen && <p className="mt-1 text-muted">{r.algemeen}</p>}
                  {Object.entries(r.items ?? {}).length > 0 && (
                    <ul className="mt-1 space-y-0.5">
                      {Object.entries(r.items).map(([id, opm]) => (
                        <li key={id} className="text-muted">
                          <span className="font-mono text-xs text-faint">{id}:</span> {opm}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    </Section>
  );
}
