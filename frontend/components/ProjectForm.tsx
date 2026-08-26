"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card } from "@/components/ui/Card";
import { Combobox } from "@/components/ui/Combobox";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { createProject, getArtikelInfo, isApiError, listModelProfiles, listWetten } from "@/lib/api";
import { bestaatArtikel } from "@/lib/artikelFilter";
import {
  buildStartRequest, legeBron, parseBegrippenlijst, projectSchema,
  type BronFormValue, type ParseResultaat,
} from "@/lib/projectForm";
import { pathSegment } from "@/lib/url";
import { useWetStructuren, type StructuurEntry } from "@/lib/useWetStructuur";
import type { ArtikelInfo, ProfileChoice, WetChoice } from "@/lib/types";

export function ProjectForm() {
  const router = useRouter();
  const [review, setReview] = useState(true);
  const [bezig, setBezig] = useState(false);
  const [veldFout, setVeldFout] = useState<Record<string, string>>({});
  const [fout, setFout] = useState<string | null>(null);
  const [profielen, setProfielen] = useState<ProfileChoice[] | null>(null);
  const [profiel, setProfiel] = useState("");
  const [wetten, setWetten] = useState<WetChoice[] | null>(null);
  // Het werkgebied: één of meer bronnen (wet + artikel + lid).
  const [bronnen, setBronnen] = useState<BronFormValue[]>([legeBron()]);
  // Bestaande begrippenlijst (optioneel): geplakt of geüpload, client-side geparseerd.
  const [begrippenTekst, setBegrippenTekst] = useState("");
  const begrippenParse: ParseResultaat = parseBegrippenlijst(begrippenTekst);
  const heeftCatalogus = wetten !== null && wetten.length > 0;
  // Wetsstructuur per BWB-id (gedeeld over rijen op dezelfde wet) voor de artikel-combobox;
  // een catalogus-keuze is meteen compleet, vrije-tekst-invoer wordt gedebounced.
  const structuren = useWetStructuren(
    bronnen.map((b) => b.bwbId ?? ""),
    { direct: heeftCatalogus },
  );

  useEffect(() => {
    let levend = true;
    listModelProfiles()
      .then((ps) => {
        if (!levend) return;
        setProfielen(ps);
        setProfiel((ps.find((p) => p.is_default) ?? ps[0])?.name ?? "");
      })
      .catch(() => levend && setProfielen([]));
    listWetten()
      .then((ws) => levend && setWetten(ws))
      .catch(() => levend && setWetten([]));
    return () => {
      levend = false;
    };
  }, []);

  function updateBron(i: number, patch: Partial<BronFormValue>) {
    setBronnen((bs) => bs.map((b, j) => (j === i ? { ...b, ...patch } : b)));
  }
  function voegBronToe() {
    setBronnen((bs) => [...bs, legeBron()]);
  }
  function verwijderBron(i: number) {
    setBronnen((bs) => (bs.length > 1 ? bs.filter((_, j) => j !== i) : bs));
  }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFout(null);
    setVeldFout({});
    const fd = new FormData(e.currentTarget);
    if (begrippenParse.fouten.length > 0) {
      setVeldFout({ begrippenlijst: "Los eerst de parse-fouten in de begrippenlijst op." });
      return;
    }
    const raw = {
      bronnen,
      naam: String(fd.get("naam") ?? ""),
      omschrijving: String(fd.get("omschrijving") ?? ""),
      analysefocus: String(fd.get("analysefocus") ?? ""),
      begrippenlijst: begrippenParse.begrippen.length ? begrippenParse.begrippen : undefined,
      review,
      model_profile: profiel,
    };
    const parsed = projectSchema.safeParse(raw);
    if (!parsed.success) {
      const errs: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        // bron-veldfouten op "bronnen.<index>.<veld>"; overige op het topveld.
        if (issue.path[0] === "bronnen" && typeof issue.path[1] === "number") {
          errs[`bronnen.${issue.path[1]}.${String(issue.path[2] ?? "")}`] = issue.message;
        } else {
          errs[String(issue.path[0])] = issue.message;
        }
      }
      setVeldFout(errs);
      return;
    }

    // Pre-check tegen de geladen wetsstructuur (bewust niet in het Zod-schema — dat is puur):
    // een artikel dat niet in de wet bestaat, faalt hier direct i.p.v. pas tijdens de run.
    const structuurFouten: Record<string, string> = {};
    parsed.data.bronnen.forEach((b, i) => {
      const entry = structuren[(b.bwbId ?? "").trim()];
      if (entry?.status === "geladen" && entry.structuur && !bestaatArtikel(entry.structuur.artikelen, b.artikel)) {
        structuurFouten[`bronnen.${i}.artikel`] = "Artikel bestaat niet in deze wet — kies uit de lijst";
      }
    });
    if (Object.keys(structuurFouten).length > 0) {
      setVeldFout(structuurFouten);
      return;
    }

    const body = buildStartRequest(parsed.data);

    setBezig(true);
    try {
      const res = await createProject(body);
      // Invalideer de Router Cache zodat een latere terugkeer naar `/` de nieuwe analyse meteen toont
      // (anders serveert de cache de oude lijst). `bezig` blijft true tot de detailpagina rendert —
      // samen met de route-`loading.tsx` geeft dat directe navigatiefeedback.
      router.refresh();
      router.push(`/projecten/${pathSegment(res.id)}`);
    } catch (e) {
      if (isApiError(e)) {
        if (e.status === 429) setFout(`Te veel verzoeken. Probeer over ${e.retryAfter ?? "enkele"} s opnieuw.`);
        else if (e.status === 503) setFout(`De analyse-engine is niet beschikbaar: ${e.detail}`);
        else setFout(`${e.detail} (${e.status})`);
      } else {
        setFout((e as Error).message);
      }
      setBezig(false);
    }
  }

  return (
    <Card className="p-6">
      <form onSubmit={onSubmit} className="space-y-5">
        <div className="space-y-3">
          <div className="flex items-baseline justify-between">
            <span className="text-sm font-medium text-ink">Bronnen in het werkgebied</span>
            <span className="text-xs text-muted">
              {bronnen.length} bron{bronnen.length === 1 ? "" : "nen"}
            </span>
          </div>
          {veldFout.bronnen && <Melding type="fout">{veldFout.bronnen}</Melding>}

          {bronnen.map((b, i) => (
            <BronRij
              key={i}
              bron={b}
              entry={structuren[(b.bwbId ?? "").trim()]}
              heeftCatalogus={heeftCatalogus}
              wetten={wetten}
              foutBwbId={veldFout[`bronnen.${i}.bwbId`]}
              foutArtikel={veldFout[`bronnen.${i}.artikel`]}
              foutLid={veldFout[`bronnen.${i}.lid`]}
              onUpdate={(patch) => updateBron(i, patch)}
              onVerwijder={() => verwijderBron(i)}
              verwijderDisabled={bronnen.length === 1}
            />
          ))}
          <Button type="button" variant="secondary" onClick={voegBronToe}>
            + Bron toevoegen
          </Button>
        </div>

        <Field
          label="Model-profiel"
          hint={profielen === null ? "laden…" : "beheer via /beheer"}
          error={veldFout.model_profile}
        >
          {profielen && profielen.length > 0 ? (
            <Select name="model_profile" value={profiel} onChange={(e) => setProfiel(e.target.value)}>
              {profielen.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}
                  {p.is_default ? " (default)" : ""}
                </option>
              ))}
            </Select>
          ) : (
            <Input
              name="model_profile"
              value={profiel}
              onChange={(e) => setProfiel(e.target.value)}
              placeholder="azure-sonnet"
              autoComplete="off"
            />
          )}
        </Field>

        <Field label="Naam werkgebied" hint="optioneel — anders afgeleid" error={veldFout.naam}>
          <Input name="naam" placeholder="Inkomensafhankelijke bijdrage Zvw" autoComplete="off" />
        </Field>

        <Field label="Omschrijving / context" hint="optioneel" error={veldFout.omschrijving}>
          <Textarea name="omschrijving" rows={2} placeholder="Achtergrond bij deze analyse…" />
        </Field>

        <Field label="Hoofdvraag / analysefocus" hint="optioneel" error={veldFout.analysefocus}>
          <Textarea
            name="analysefocus"
            rows={2}
            placeholder="Waar moet de analyse antwoord op geven?"
          />
        </Field>

        <details className="rounded-lg border border-line bg-paper/60 p-3">
          <summary className="cursor-pointer text-sm font-medium text-ink">
            Bestaande begrippenlijst (optioneel)
            {begrippenParse.begrippen.length > 0 && (
              <span className="ml-2 font-mono text-xs text-faint">
                {begrippenParse.begrippen.length} begrip
                {begrippenParse.begrippen.length === 1 ? "" : "pen"} herkend
              </span>
            )}
          </summary>
          <div className="mt-3 space-y-2">
            <p className="text-xs text-muted">
              Plak of upload een bestaande begrippenlijst als suggestieve invoer voor activiteit 3:
              JSON (<code>{"{begrippen: [...]}"}</code>), CSV met kopregel (kolom <code>naam</code>{" "}
              verplicht), of één begrip per regel (<code>naam; definitie</code>). De analyse
              hergebruikt waar de betekenis past en registreert per begrip de herkomst.
            </p>
            <Textarea
              value={begrippenTekst}
              onChange={(e) => setBegrippenTekst(e.target.value)}
              rows={5}
              placeholder={"belastingplichtige; degene die aangifte moet doen\nbijdrage-inkomen"}
            />
            <input
              type="file"
              accept=".json,.csv,.txt"
              className="block w-full text-sm text-muted file:mr-3 file:rounded-md file:border file:border-line file:bg-paper file:px-3 file:py-1.5 file:text-sm file:text-ink"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                const reader = new FileReader();
                reader.onload = () => setBegrippenTekst(String(reader.result ?? ""));
                reader.readAsText(f);
              }}
            />
            {begrippenParse.fouten.length > 0 && (
              <Melding type="fout">
                <ul className="list-inside list-disc space-y-0.5">
                  {begrippenParse.fouten.slice(0, 5).map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                  {begrippenParse.fouten.length > 5 && (
                    <li>… en {begrippenParse.fouten.length - 5} meer</li>
                  )}
                </ul>
              </Melding>
            )}
            {veldFout.begrippenlijst && <Melding type="fout">{veldFout.begrippenlijst}</Melding>}
          </div>
        </details>

        <label className="flex items-start gap-3 rounded-lg border border-line bg-paper/60 p-3">
          <input
            type="checkbox"
            checked={review}
            onChange={(e) => setReview(e.target.checked)}
            className="mt-0.5 h-4 w-4 accent-accent"
          />
          <span className="text-sm">
            <span className="font-medium text-ink">Human-in-the-loop review</span>
            <span className="mt-0.5 block text-muted">
              Pauzeer na activiteit 2 en 3 voor jouw beoordeling. Uit = volautomatisch tot het
              rapport (brongetrouwheid blijft hard afgedwongen).
            </span>
          </span>
        </label>

        {fout && <Melding type="fout">{fout}</Melding>}

        <ButtonRow className="pt-2">
          <Button type="submit" disabled={bezig}>
            {bezig ? "Bezig met starten…" : "Analyse starten"}
          </Button>
        </ButtonRow>
      </form>
    </Card>
  );
}

interface BronRijProps {
  bron: BronFormValue;
  entry?: StructuurEntry;
  heeftCatalogus: boolean;
  wetten: WetChoice[] | null;
  foutBwbId?: string;
  foutArtikel?: string;
  foutLid?: string;
  onUpdate: (patch: Partial<BronFormValue>) => void;
  onVerwijder: () => void;
  verwijderDisabled: boolean;
}

/**
 * Eén bron-rij (wet + artikel + lid). Is de wetsstructuur geladen, dan wordt artikel een
 * combobox met autocomplete en lid een keuzelijst met de echte leden (+ een bevestigings-
 * regel met opschrift en tekstsnippet). Faalt de structuur- of artikelinfo-lookup, dan
 * degradeert de rij naar de vrije-tekstvelden — het formulier blijft altijd bruikbaar.
 */
function BronRij({
  bron, entry, heeftCatalogus, wetten,
  foutBwbId, foutArtikel, foutLid,
  onUpdate, onVerwijder, verwijderDisabled,
}: BronRijProps) {
  const bwbId = (bron.bwbId ?? "").trim();
  const artikel = (bron.artikel ?? "").trim();
  const items = entry?.status === "geladen" ? entry.structuur?.artikelen ?? null : null;
  const [info, setInfo] = useState<ArtikelInfo | null>(null);

  // Zodra het getypte/gekozen artikel in de structuur bestaat: ledeninfo ophalen voor de
  // lid-keuzelijst + bevestigingsregel. Kort gedebounced tegen churn bij doortypen (9 → 9a).
  useEffect(() => {
    setInfo(null);
    if (!items) return;
    const canoniek = items.find((it) => it.artikel.toLowerCase() === artikel.toLowerCase())?.artikel;
    if (!canoniek) return;
    let levend = true;
    const t = setTimeout(() => {
      getArtikelInfo(bwbId, canoniek)
        .then((i) => levend && setInfo(i))
        .catch(() => {
          /* lid blijft vrije invoer */
        });
    }, 300);
    return () => {
      levend = false;
      clearTimeout(t);
    };
  }, [bwbId, artikel, items]);

  const artikelHint =
    entry?.status === "laden" ? "artikelen laden…" :
    entry?.status === "fout" ? "lijst niet beschikbaar — vrije invoer" : undefined;

  return (
    <div className="grid grid-cols-1 gap-3 rounded-lg border border-line bg-paper/60 p-3 sm:grid-cols-[1fr_auto_auto_auto]">
      <Field label="Wet" error={foutBwbId}>
        {heeftCatalogus ? (
          <Select
            value={bron.bwbId}
            onChange={(e) => onUpdate({ bwbId: e.target.value, artikel: "", lid: "" })}
          >
            <option value="">— kies een wet —</option>
            {wetten!.map((w) => (
              <option key={w.bwbId} value={w.bwbId}>
                {w.naam || w.bwbId}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            value={bron.bwbId}
            onChange={(e) => onUpdate({ bwbId: e.target.value, artikel: "", lid: "" })}
            placeholder="BWBR0004770"
            autoComplete="off"
          />
        )}
      </Field>
      <Field label="Artikel" required hint={artikelHint} error={foutArtikel}>
        {items ? (
          <Combobox
            value={bron.artikel}
            onChange={(t) => onUpdate({ artikel: t, lid: "" })}
            items={items}
            placeholder="9"
            className="sm:w-32"
          />
        ) : (
          <Input
            value={bron.artikel}
            onChange={(e) => onUpdate({ artikel: e.target.value, lid: "" })}
            placeholder="9"
            autoComplete="off"
            className="sm:w-32"
          />
        )}
      </Field>
      <Field label="Lid" hint="optioneel" error={foutLid}>
        {info ? (
          <Select
            value={bron.lid}
            onChange={(e) => onUpdate({ lid: e.target.value })}
            className="sm:w-36"
          >
            <option value="">Hele artikel</option>
            {info.leden.map((l) => (
              <option key={l} value={l}>
                Lid {l}
              </option>
            ))}
          </Select>
        ) : (
          <Input
            value={bron.lid}
            onChange={(e) => onUpdate({ lid: e.target.value })}
            placeholder="2"
            autoComplete="off"
            className="sm:w-20"
          />
        )}
      </Field>
      <div className="flex items-end">
        <Button
          type="button"
          variant="secondary"
          onClick={onVerwijder}
          disabled={verwijderDisabled}
          aria-label="Bron verwijderen"
        >
          ×
        </Button>
      </div>
      {info && (
        <p className="text-xs text-muted sm:col-span-4">
          <span className="font-medium text-ink">{info.opschrift || `Artikel ${info.artikel}`}</span>
          {info.pad ? ` · ${info.pad}` : ""}
          {info.snippet ? ` — ${info.snippet}` : ""}
        </p>
      )}
    </div>
  );
}
