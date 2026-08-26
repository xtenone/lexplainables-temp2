"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { JasBadge } from "@/components/ui/Badge";
import { Textarea } from "@/components/ui/Field";
import { LedenLijst } from "@/components/LedenLijst";
import { getRonde, sendFeedback, isApiError } from "@/lib/api";
import {
  begripNaamMap, herkomstLabel, regelVelden, relatiesText, verwijstNaarText,
} from "@/lib/begrippen";
import { bronLabelMap, vindplaatsText } from "@/lib/bronnen";
import { jasVolgorde } from "@/lib/jas";
import type {
  Activiteit, Analyse2, Analyse3, Bron, Feedback, GegevensSpraak, Job, Lid, RsRegel,
} from "@/lib/types";

/** Alle leden van alle bronnen samen, als wettekst-context voor de review. */
function ledenUitBronnen(bronnen: Bron[] | undefined): Lid[] {
  return (bronnen ?? []).flatMap((b) => b.leden ?? []);
}

interface ReviewItem {
  id: string;
  titel: string;
  klasse?: string;
  soort?: string;
  regels: { label: string; waarde: string }[];
  twijfel?: string;
}

/** Splits de mechanische waarschuwingen in item-specifieke (prefix "[id]") en algemene. */
function splitsWaarschuwingen(ws: string[]): { perId: Record<string, string[]>; algemeen: string[] } {
  const perId: Record<string, string[]> = {};
  const algemeen: string[] = [];
  const re = /^\[([^\]]+)\]\s*/;
  for (const w of ws) {
    const m = re.exec(w);
    if (m) (perId[m[1]] ??= []).push(w.slice(m[0].length));
    else algemeen.push(w);
  }
  return { perId, algemeen };
}

/** ReviewItems voor de RegelSpraak-stappen (GegevensSpraak / regels). */
function itemsUitRegelspraak(act: "rs-gegevens" | "rs-regels", data: unknown): ReviewItem[] {
  if (act === "rs-gegevens") {
    const gs = ((data as { gegevensspraak?: GegevensSpraak })?.gegevensspraak ?? {}) as GegevensSpraak;
    const out: ReviewItem[] = [];
    for (const o of gs.objecttypen ?? []) {
      out.push({
        id: o.id, titel: o.naam || o.id, klasse: "objecttype", soort: "gegeven",
        regels: [
          { label: "Attributen", waarde: (o.attributen ?? []).map((a) => a.naam).join(", ") },
          { label: "Kenmerken", waarde: (o.kenmerken ?? []).map((k) => k.naam).join(", ") },
          { label: "RegelSpraak", waarde: o.regelspraak_tekst ?? "" },
        ],
        twijfel: o.twijfel,
      });
    }
    for (const f of gs.feittypen ?? []) {
      out.push({
        id: f.id, titel: f.naam || f.id, klasse: "feittype", soort: "gegeven",
        regels: [
          { label: "Rollen", waarde: (f.rollen ?? []).map((r) => r.naam).join(", ") },
          { label: "RegelSpraak", waarde: f.regelspraak_tekst ?? "" },
        ],
      });
    }
    for (const p of gs.parameters ?? []) {
      out.push({
        id: p.id, titel: p.naam || p.id, klasse: "parameter", soort: "gegeven",
        regels: [
          { label: "Datatype", waarde: p.datatype },
          { label: "RegelSpraak", waarde: p.regelspraak_tekst ?? "" },
        ],
      });
    }
    return out;
  }
  const regels = ((data as { regels?: RsRegel[] })?.regels ?? []) as RsRegel[];
  return regels.map((r) => ({
    id: r.id, titel: r.naam || r.id, klasse: r.soort, soort: "regel",
    regels: [{ label: "RegelSpraak", waarde: r.regelspraak_tekst ?? "" }],
    twijfel: r.twijfel,
  }));
}

function itemsUitAnalyse(act: Activiteit, data: unknown): ReviewItem[] {
  if (act === "rs-gegevens" || act === "rs-regels") {
    return itemsUitRegelspraak(act, data);
  }
  return items2of3(act, data as Analyse2 | Analyse3);
}

function items2of3(act: "2" | "3", data: Analyse2 | Analyse3): ReviewItem[] {
  if (act === "2") {
    const a = data as Analyse2;
    const labels = bronLabelMap(a.bronnen);
    const out: ReviewItem[] = [];
    for (const bron of a.bronnen ?? []) {
      const bronNaam = labels[bron.bron_id] || bron.label;
      const markeringen = [...(bron.markeringen ?? [])].sort(
        (x, y) => jasVolgorde(x.klasse) - jasVolgorde(y.klasse),
      );
      for (const m of markeringen) {
        out.push({
          id: m.id,
          titel: m.formulering || m.id,
          klasse: m.klasse,
          soort: "markering",
          regels: [
            { label: "Bron", waarde: bronNaam },
            { label: "Vindplaats", waarde: m.vindplaats },
            { label: "Toelichting", waarde: m.toelichting },
          ],
          twijfel: m.twijfel,
        });
      }
      for (const v of bron.verwijzingen ?? []) {
        out.push({
          id: v.id,
          titel: v.doel?.label || v.functie || v.id,
          soort: "verwijzing",
          regels: [
            { label: "Bron", waarde: bronNaam },
            { label: "Functie", waarde: v.functie },
            { label: "Status", waarde: v.status },
            { label: "Betekenis", waarde: v.betekenis },
          ],
        });
      }
    }
    return out;
  }
  const a = data as Analyse3;
  const labels = bronLabelMap(a.bronnen);
  const namen = begripNaamMap(a.begrippen);
  const begrippen: ReviewItem[] = [...(a.begrippen ?? [])]
    .sort((x, y) => jasVolgorde(x.klasse) - jasVolgorde(y.klasse))
    .map((b) => ({
    id: b.id,
    titel: b.naam || b.id,
    klasse: b.klasse,
    regels: [
      { label: "Synoniemen", waarde: (b.synoniemen ?? []).join(", ") },
      {
        label: "Definitie",
        waarde: b.definitie + (b.is_interpretatie ? " [interpretatie]" : ""),
      },
      { label: "Grondformulering", waarde: b.grondformulering },
      { label: "Kenmerken", waarde: b.kenmerken },
      { label: "Relaties", waarde: relatiesText(b.relaties, namen) },
      { label: "Verwijst naar", waarde: verwijstNaarText(b.verwijst_naar_begrippen, namen) },
      { label: "Bron-verwijzing", waarde: b.bron_verwijzing ?? "" },
      { label: "Markeringen", waarde: (b.markering_ids ?? []).join(", ") },
      { label: "Herkomst", waarde: herkomstLabel(b.herkomst) + (b.herkomst?.motivatie ? ` — ${b.herkomst.motivatie}` : "") },
      { label: "Vindplaats", waarde: vindplaatsText(b.vindplaatsen, labels) },
    ],
    twijfel: b.twijfel,
  }));
  const regels: ReviewItem[] = (a.afleidingsregels ?? []).map((r) => ({
    id: r.id,
    titel: r.naam || r.id,
    klasse: r.type,
    regels: [
      ...regelVelden(r, namen),
      { label: "Markeringen", waarde: (r.markering_ids ?? []).join(", ") },
      { label: "Vindplaats", waarde: vindplaatsText(r.vindplaatsen, labels) },
    ],
    twijfel: r.twijfel,
  }));
  return [...begrippen, ...regels];
}

export function ReviewPanel({
  job,
  activiteit,
  onSubmitted,
  onDelete,
  verwijderBezig,
}: {
  job: Job;
  activiteit: Activiteit;
  onSubmitted: () => void | Promise<void>;
  /** Gooi de hele analyse weg (incl. bevestiging) — afgehandeld door de ouder. */
  onDelete?: () => void | Promise<void>;
  verwijderBezig?: boolean;
}) {
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [leden, setLeden] = useState<Lid[] | null>(null);
  const [laadFout, setLaadFout] = useState<string | null>(null);
  const [opmerkingen, setOpmerkingen] = useState<Record<string, string>>({});
  const [algemeen, setAlgemeen] = useState("");
  const [bezig, setBezig] = useState<null | Feedback["status"]>(null);
  const [fout, setFout] = useState<string | null>(null);

  const ronde = job.current_ronde || 1;
  const { perId: waarschuwingenPerId, algemeen: algemeneWaarschuwingen } = splitsWaarschuwingen(
    job.waarschuwingen,
  );

  useEffect(() => {
    let actief = true;
    (async () => {
      try {
        const d = await getRonde(job.id, activiteit, ronde);
        if (!actief) return;
        setItems(itemsUitAnalyse(activiteit, d));
        // Wettekst als context. Bij activiteit 2 zit 'leden' in de ronde zelf; bij de andere
        // stappen (act 3, regelspraak) niet, maar de brongetrouwe wettekst is in elke
        // activiteit-2-ronde identiek → haal 'm best-effort uit ronde 1 van activiteit 2.
        if (activiteit === "2") {
          setLeden(ledenUitBronnen((d as Analyse2).bronnen));
        } else {
          try {
            const a2 = await getRonde(job.id, "2", 1);
            if (actief) setLeden(ledenUitBronnen((a2 as Analyse2).bronnen));
          } catch {
            /* wettekst is context, geen blocker */
          }
        }
      } catch (e) {
        if (actief) setLaadFout(isApiError(e) ? e.detail : (e as Error).message);
      }
    })();
    return () => {
      actief = false;
    };
  }, [job.id, activiteit, ronde]);

  async function verstuur(status: Feedback["status"]) {
    setFout(null);
    const ingevuld: Record<string, string> = {};
    for (const [k, v] of Object.entries(opmerkingen)) if (v.trim()) ingevuld[k] = v.trim();

    if (status === "wijzigingen" && Object.keys(ingevuld).length === 0 && !algemeen.trim()) {
      setFout("Geef minstens één opmerking of een algemene opmerking om wijzigingen in te dienen.");
      return;
    }

    const body: Feedback = {
      status,
      activiteit,
      items: status === "wijzigingen" ? ingevuld : {},
      algemeen: status === "wijzigingen" ? algemeen.trim() : "",
    };
    setBezig(status);
    try {
      await sendFeedback(job.id, body);
      await onSubmitted();
    } catch (e) {
      if (isApiError(e) && e.status === 409) setFout("De status is intussen veranderd; de pagina ververst.");
      else setFout(isApiError(e) ? e.detail : (e as Error).message);
      await onSubmitted();
    }
    setBezig(null);
  }

  const titel =
    activiteit === "2"
      ? "Review activiteit 2 — markeringen & classificaties"
      : activiteit === "3"
        ? "Review activiteit 3 — begrippen & afleidingsregels"
        : activiteit === "rs-gegevens"
          ? "Review RegelSpraak — GegevensSpraak (objectmodel)"
          : "Review RegelSpraak — regels";

  return (
    <Card className="p-6">
      <div className="mb-1 flex items-baseline justify-between gap-3">
        <h2 className="font-display text-lg font-semibold text-lint">{titel}</h2>
        <span className="font-mono text-xs text-faint">ronde {ronde}</span>
      </div>
      <p className="mb-5 max-w-prose text-sm text-muted">
        Beoordeel elk item. Laat een veld leeg als je akkoord bent. Bij twijfel van de analyse staat
        een geel kader. Kies daarna <em>Akkoord</em> (door naar de volgende fase) of{" "}
        <em>Wijzigingen indienen</em> (nieuwe ronde met jouw opmerkingen).
        {activiteit === "2" && (
          <>
            {" "}Wil je alleen de markeringen en classificaties vastleggen, kies dan{" "}
            <em>Akkoord — afronden zonder act. 3</em>; activiteit 3 kan later alsnog.
          </>
        )}
      </p>

      {laadFout && (
        <Melding type="fout" className="mb-4">
          Kon de ronde niet laden: {laadFout}
        </Melding>
      )}

      {algemeneWaarschuwingen.length > 0 && (
        <Melding type="waarschuwing" titel="Aandachtspunten bij deze ronde" className="mb-4">
          <ul className="mt-1 list-inside list-disc space-y-0.5">
            {algemeneWaarschuwingen.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Melding>
      )}

      {leden && leden.length > 0 && (
        <details open className="mb-4 rounded-lg border border-line bg-paper/50 p-4">
          <summary className="cursor-pointer text-sm font-medium text-ink">
            Wettekst (letterlijk) — context
          </summary>
          <div className="mt-3">
            <LedenLijst leden={leden} />
          </div>
        </details>
      )}

      {!items && !laadFout && <p className="text-sm text-muted">Laden…</p>}

      <div className="space-y-3">
        {items?.map((it) => (
          <div key={it.id} className="rounded-lg border border-line bg-paper/50 p-4">
            <div className="flex flex-col items-start gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-3">
              <div className="min-w-0 w-full sm:w-auto">
                <p className="break-words font-medium text-ink">{it.titel}</p>
                <span className="font-mono text-xs text-faint">
                  {it.id}
                  {it.soort === "verwijzing" ? " · verwijzing" : ""}
                </span>
              </div>
              {it.klasse && <JasBadge klasse={it.klasse} />}
            </div>
            <dl className="mt-2 space-y-1 text-sm">
              {it.regels
                .filter((r) => r.waarde)
                .map((r) => (
                  <div key={r.label} className="flex gap-2">
                    <dt className="w-28 shrink-0 text-xs uppercase tracking-wide text-faint">{r.label}</dt>
                    <dd className="min-w-0 break-words text-muted">{r.waarde}</dd>
                  </div>
                ))}
            </dl>
            {it.twijfel && (
              <Melding type="waarschuwing" compact className="mt-2 text-xs">
                Twijfel: {it.twijfel}
              </Melding>
            )}
            {waarschuwingenPerId[it.id]?.map((w, i) => (
              <Melding key={i} type="waarschuwing" compact className="mt-2 text-xs">
                Let op: {w}
              </Melding>
            ))}
            <Textarea
              value={opmerkingen[it.id] ?? ""}
              onChange={(e) => setOpmerkingen((o) => ({ ...o, [it.id]: e.target.value }))}
              rows={2}
              placeholder="Opmerking (leeg = akkoord)…"
              className="mt-3 bg-surface"
            />
          </div>
        ))}
      </div>

      <div className="mt-5">
        <label className="mb-1 block text-sm font-medium text-ink">Algemene opmerking</label>
        <Textarea
          value={algemeen}
          onChange={(e) => setAlgemeen(e.target.value)}
          rows={2}
          placeholder="Overkoepelende opmerkingen voor deze activiteit…"
        />
      </div>

      {fout && (
        <Melding type="fout" className="mt-4">
          {fout}
        </Melding>
      )}

      <div className="mt-5 flex flex-col-reverse gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
        {onDelete ? (
          <Button
            variant="danger"
            onClick={() => onDelete()}
            disabled={bezig !== null || verwijderBezig}
            title="Verwijder deze analyse definitief"
            className="w-full sm:w-auto"
          >
            {verwijderBezig ? "Verwijderen…" : "Analyse verwijderen"}
          </Button>
        ) : (
          <span />
        )}
        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center">
          <Button
            variant="secondary"
            onClick={() => verstuur("wijzigingen")}
            disabled={bezig !== null || verwijderBezig || !items}
            className="w-full sm:w-auto"
          >
            {bezig === "wijzigingen" ? "Versturen…" : "Wijzigen"}
          </Button>
          {activiteit === "2" && (
            <Button
              variant="secondary"
              onClick={() => verstuur("akkoord-afronden")}
              disabled={bezig !== null || verwijderBezig || !items}
              title="Keur activiteit 2 goed en rond de analyse hier af — begrippen en afleidingsregels (activiteit 3) worden niet opgesteld; dat kan later alsnog."
              className="w-full sm:w-auto"
            >
              {bezig === "akkoord-afronden" ? "Versturen…" : "Akkoord — afronden zonder act. 3"}
            </Button>
          )}
          <Button
            onClick={() => verstuur("akkoord")}
            disabled={bezig !== null || verwijderBezig || !items}
            className="w-full sm:w-auto"
          >
            {bezig === "akkoord" ? "Versturen…" : "Akkoord"}
          </Button>
        </div>
      </div>
    </Card>
  );
}
