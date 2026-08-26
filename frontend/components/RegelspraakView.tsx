"use client";

import { Card, Section } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import type {
  RegelspraakHerkomst, RegelspraakModel, RsFeittype, RsObjecttype, RsParameter, RsRegel,
} from "@/lib/types";

function herkomstTekst(h?: RegelspraakHerkomst): string {
  if (!h) return "";
  const refs: string[] = [];
  if (h.begrip_ids?.length) refs.push(h.begrip_ids.join(", "));
  if (h.regel_id) refs.push(h.regel_id);
  const vp = (h.vindplaatsen ?? [])
    .map((v) => `${v.bron_id}${v.lid ? ` lid ${v.lid}` : ""}`)
    .join("; ");
  return [refs.join(", "), vp].filter(Boolean).join(" · ");
}

/** Letterlijke RegelSpraak-tekst in een monospace-blok. */
function RsBlok({ tekst }: { tekst?: string }) {
  if (!tekst) return null;
  return (
    <pre className="mt-2 overflow-x-auto whitespace-pre-wrap rounded-lg border border-line bg-paper/60 p-3 font-mono text-xs text-ink">
      {tekst}
    </pre>
  );
}

function Herkomst({ h }: { h?: RegelspraakHerkomst }) {
  const t = herkomstTekst(h);
  if (!t) return null;
  return <p className="mt-1 font-mono text-xs text-faint">herkomst: {t}</p>;
}

function Twijfel({ tekst }: { tekst?: string }) {
  if (!tekst) return null;
  return (
    <Melding type="waarschuwing" compact className="mt-2 text-xs">
      Twijfel: {tekst}
    </Melding>
  );
}

function ObjecttypeKaart({ o }: { o: RsObjecttype }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 break-words font-display text-base font-medium text-ink">{o.naam}</p>
        {o.bezield && <Tag>bezield</Tag>}
      </div>
      {(o.attributen?.length ?? 0) > 0 && (
        <p className="mt-1 text-sm text-muted">
          <span className="text-xs uppercase tracking-wide text-faint">Attributen: </span>
          {(o.attributen ?? [])
            .map((a) => {
              const type = [a.datatype, a.eenheid].filter(Boolean).join(", ");
              return type ? `${a.naam} (${type})` : a.naam;
            })
            .join(", ")}
        </p>
      )}
      {(o.kenmerken?.length ?? 0) > 0 && (
        <p className="mt-1 text-sm text-muted">
          <span className="text-xs uppercase tracking-wide text-faint">Kenmerken: </span>
          {(o.kenmerken ?? []).map((k) => k.naam).join(", ")}
        </p>
      )}
      <RsBlok tekst={o.regelspraak_tekst} />
      <Herkomst h={o.herkomst} />
      <Twijfel tekst={o.twijfel} />
    </Card>
  );
}

function FeittypeKaart({ f }: { f: RsFeittype }) {
  return (
    <Card className="p-4">
      <p className="font-display text-base font-medium text-ink">{f.naam}</p>
      {(f.rollen?.length ?? 0) > 0 && (
        <p className="mt-1 text-sm text-muted">
          <span className="text-xs uppercase tracking-wide text-faint">Rollen: </span>
          {(f.rollen ?? []).map((r) => `${r.naam}${r.objecttype ? ` (${r.objecttype})` : ""}`).join(", ")}
        </p>
      )}
      <RsBlok tekst={f.regelspraak_tekst} />
      <Herkomst h={f.herkomst} />
    </Card>
  );
}

function ParameterKaart({ p }: { p: RsParameter }) {
  return (
    <Card className="p-4">
      <p className="font-display text-base font-medium text-ink">{p.naam}</p>
      {p.datatype && (
        <p className="mt-1 text-sm text-muted">
          <span className="text-xs uppercase tracking-wide text-faint">Datatype: </span>
          {p.datatype}
        </p>
      )}
      <RsBlok tekst={p.regelspraak_tekst} />
      <Herkomst h={p.herkomst} />
    </Card>
  );
}

function RegelKaart({ r }: { r: RsRegel }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 break-words font-display text-base font-medium text-ink">{r.naam}</p>
        {r.soort && <Tag>{r.soort}</Tag>}
      </div>
      <RsBlok tekst={r.regelspraak_tekst} />
      <Herkomst h={r.herkomst} />
      <Twijfel tekst={r.twijfel} />
    </Card>
  );
}

export function RegelspraakView({ model }: { model: RegelspraakModel }) {
  const gs = model.gegevensspraak ?? {};
  return (
    <div className="space-y-6">
      {/* Fase-kop: h2 */}
      <Card className="p-6">
        <h2 className="font-display text-xl font-semibold text-lint">RegelSpraak-specificatie</h2>
        <p className="mt-1 text-sm text-muted">GegevensSpraak + regels</p>
        {model.werkgebied?.naam && (
          <div className="mt-3 flex flex-wrap gap-2">
            <Tag>{model.werkgebied.naam}</Tag>
          </div>
        )}
      </Card>

      {(gs.domeinen?.length ?? 0) > 0 && (
        <Section title="Domeinen" count={gs.domeinen!.length} level={3}>
          <div className="space-y-3">
            {gs.domeinen!.map((d, i) => (
              <Card key={i} className="p-4">
                <p className="font-display text-base font-medium text-ink">{d.naam}</p>
                <RsBlok tekst={d.regelspraak_tekst} />
                <Herkomst h={d.herkomst} />
              </Card>
            ))}
          </div>
        </Section>
      )}

      {(gs.objecttypen?.length ?? 0) > 0 && (
        <Section title="Objecttypen" count={gs.objecttypen!.length} level={3}>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {gs.objecttypen!.map((o, i) => (
              <ObjecttypeKaart key={`${o.id}-${i}`} o={o} />
            ))}
          </div>
        </Section>
      )}

      {(gs.feittypen?.length ?? 0) > 0 && (
        <Section title="Feittypen" count={gs.feittypen!.length} level={3}>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {gs.feittypen!.map((f, i) => (
              <FeittypeKaart key={`${f.id}-${i}`} f={f} />
            ))}
          </div>
        </Section>
      )}

      {(gs.parameters?.length ?? 0) > 0 && (
        <Section title="Parameters" count={gs.parameters!.length} level={3}>
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            {gs.parameters!.map((p, i) => (
              <ParameterKaart key={`${p.id}-${i}`} p={p} />
            ))}
          </div>
        </Section>
      )}

      {(model.regels?.length ?? 0) > 0 && (
        <Section title="RegelSpraak-regels" count={model.regels.length} level={3}>
          <div className="space-y-3">
            {model.regels.map((r, i) => (
              <RegelKaart key={`${r.id}-${i}`} r={r} />
            ))}
          </div>
        </Section>
      )}

      {(model.validatiepunten?.length ?? 0) > 0 && (
        <Section title="Validatiepunten" count={model.validatiepunten.length} level={3}>
          <Card className="p-4">
            <ul className="list-inside list-disc space-y-1 text-sm text-muted">
              {model.validatiepunten.map((v, i) => (
                <li key={i}>{v}</li>
              ))}
            </ul>
          </Card>
        </Section>
      )}
    </div>
  );
}
