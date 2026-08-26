"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { StateBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { ProjectControls } from "@/components/ProjectControls";
import { Pagination } from "@/components/Pagination";
import { useProjectenStream } from "@/lib/useProjectenStream";
import { bronnenSamenvatting } from "@/lib/bronnen";
import { deleteProject, isApiError } from "@/lib/api";
import { isDeletable } from "@/lib/states";
import { pathSegment } from "@/lib/url";
import {
  DEFAULT_FILTERS,
  distinctWetten,
  filterEnSorteer,
  paginate,
  type ProjectFilters,
} from "@/lib/projectFilter";
import type { JobSummary } from "@/lib/types";

const PAGE_SIZE = 25;

/** Tijdstip in Europe/Amsterdam, expliciet en niet in de tijdzone van de omgeving. De server draait
 *  in UTC (Docker) terwijl analisten in NL werken: zonder vaste `timeZone` rendert de SSR een
 *  UTC-tijd en de browser een lokale, wat 's zomers twee uur scheelt én een hydration-mismatch
 *  oplevert. Eén vaste zone lost beide op. Zelfde afweging als `vandaag()` in
 *  `tools/wettenbank-mcp/src/shared/utils.ts`. Geëxporteerd om testbaar te zijn. */
export function formatDatum(iso: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("nl-NL", {
    timeZone: "Europe/Amsterdam",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Live projectenlijst: geseed uit de SSR-render, daarna bijgewerkt via de gedeelde aggregate-SSE
 *  (nieuwe analyses verschijnen vanzelf, statussen lopen mee, verwijderde rijen verdwijnen). Zoeken,
 *  filteren, sorteren en pagineren gebeuren client-side op de live lijst. */
export function ProjectenLijstClient({ initieel }: { initieel: JobSummary[] }) {
  const router = useRouter();
  const { items, verwijderLokaal } = useProjectenStream(initieel);
  const all = [...items.values()];

  // Re-sync de SSR-lijst bij terugkeer naar het tabblad/venster: een analyse die elders is aangemaakt
  // (of de stand na een trage SSE-(her)verbinding) verschijnt zo meteen. Gethrottled zodat snel
  // wisselen niet bij elke event een refetch triggert; de verse `initieel` wordt door
  // `useProjectenStream` in de lijst opgenomen.
  const laatsteRefresh = useRef(0);
  useEffect(() => {
    const refresh = () => {
      if (document.visibilityState !== "visible") return;
      const nu = Date.now();
      if (nu - laatsteRefresh.current < 3000) return;
      laatsteRefresh.current = nu;
      router.refresh();
    };
    document.addEventListener("visibilitychange", refresh);
    window.addEventListener("focus", refresh);
    return () => {
      document.removeEventListener("visibilitychange", refresh);
      window.removeEventListener("focus", refresh);
    };
  }, [router]);

  const [filters, setFilters] = useState<ProjectFilters>(DEFAULT_FILTERS);
  const [page, setPage] = useState(1);
  useEffect(() => setPage(1), [filters]);

  const wetten = distinctWetten(all);
  const gefilterd = filterEnSorteer(all, filters);
  const { items: lijst, page: huidige, totalPages, total } = paginate(gefilterd, page, PAGE_SIZE);
  useEffect(() => {
    if (page !== huidige) setPage(huidige);
  }, [page, huidige]);

  // Multi-select + bulk verwijderen. De selectie leeft op id en overleeft pagina-/filterwissels;
  // rijen die intussen verdwenen zijn (SSE `removed`, ander tabblad) vallen er bij afleiding uit.
  const [geselecteerd, setGeselecteerd] = useState<Set<string>>(new Set());
  const [bezig, setBezig] = useState<{ k: number; n: number } | null>(null);
  const [resultaat, setResultaat] = useState<{
    type: "bevestiging" | "waarschuwing" | "fout";
    tekst: string;
    fouten?: { naam: string; detail: string }[];
  } | null>(null);

  const selectie = new Set([...geselecteerd].filter((id) => items.has(id)));
  const paginaSelecteerbaar = lijst.filter((p) => isDeletable(p.state));
  const alleOpPagina =
    paginaSelecteerbaar.length > 0 && paginaSelecteerbaar.every((p) => selectie.has(p.id));
  const enkeleOpPagina = paginaSelecteerbaar.some((p) => selectie.has(p.id));

  function toggle(id: string) {
    setResultaat(null);
    setGeselecteerd((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function togglePagina() {
    setResultaat(null);
    setGeselecteerd((prev) => {
      const next = new Set(prev);
      if (alleOpPagina) for (const p of paginaSelecteerbaar) next.delete(p.id);
      else for (const p of paginaSelecteerbaar) next.add(p.id);
      return next;
    });
  }

  function wisSelectie() {
    setResultaat(null);
    setGeselecteerd(new Set());
  }

  async function verwijderSelectie() {
    const ids = [...selectie];
    const n = ids.length;
    if (n === 0) return;
    if (!confirm(`${n} analyse${n === 1 ? "" : "s"} verwijderen? Dit kan niet ongedaan worden gemaakt.`)) {
      return;
    }
    setResultaat(null);
    const geslaagd = new Set<string>();
    const fouten: { naam: string; detail: string }[] = [];
    try {
      for (let i = 0; i < ids.length; i++) {
        const id = ids[i];
        setBezig({ k: i + 1, n });
        try {
          await deleteProject(id);
          geslaagd.add(id);
        } catch (e) {
          // 404 = al verwijderd (ander tabblad): het doel is bereikt.
          if (isApiError(e) && e.status === 404) {
            geslaagd.add(id);
          } else {
            const naam = items.get(id)?.naam || id;
            fouten.push({ naam, detail: isApiError(e) ? e.detail : (e as Error).message });
          }
        }
      }
    } finally {
      setBezig(null);
    }
    // Verwijder de geslaagde rijen direct lokaal (optimistisch): meteen weg uit de lijst, ook als de
    // aggregate-SSE net down is (de `removed`-events zouden dan uitblijven).
    verwijderLokaal([...geslaagd]);
    // Mislukte items blijven geselecteerd, zodat opnieuw proberen één klik is.
    setGeselecteerd((prev) => new Set([...prev].filter((id) => !geslaagd.has(id))));
    if (fouten.length === 0) {
      setResultaat({
        type: "bevestiging",
        tekst: `${geslaagd.size} analyse${geslaagd.size === 1 ? "" : "s"} verwijderd.`,
      });
    } else {
      setResultaat({
        type: geslaagd.size > 0 ? "waarschuwing" : "fout",
        tekst:
          geslaagd.size > 0
            ? `${geslaagd.size} verwijderd, ${fouten.length} mislukt:`
            : `Verwijderen mislukt voor ${fouten.length} analyse${fouten.length === 1 ? "" : "s"}:`,
        fouten,
      });
    }
  }

  if (all.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-3 px-6 py-16 text-center">
        <p className="font-display text-lg text-ink">Nog geen analyses</p>
        <p className="max-w-md text-sm text-muted">
          Start je eerste analyse: kies een wet en één of meer artikelen voor je werkgebied. De
          orchestrator haalt de actuele wettekst op en begeleidt je door de review-lus.
        </p>
        <LinkButton href="/nieuw" className="mt-2 w-full sm:w-auto">
          Eerste analyse starten
        </LinkButton>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <ProjectControls filters={filters} onChange={setFilters} wetten={wetten} />

      {(selectie.size > 0 || bezig) && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-line bg-surface px-4 py-2">
          <span className="text-sm text-muted">
            {selectie.size} geselecteerd
          </span>
          <Button
            variant="danger"
            size="sm"
            onClick={verwijderSelectie}
            disabled={bezig !== null || selectie.size === 0}
          >
            {bezig ? `Verwijderen… (${bezig.k}/${bezig.n})` : "Verwijderen"}
          </Button>
          <Button variant="ghost" size="sm" onClick={wisSelectie} disabled={bezig !== null}>
            Selectie wissen
          </Button>
        </div>
      )}

      {resultaat && (
        <Melding type={resultaat.type}>
          {resultaat.tekst}
          {resultaat.fouten && resultaat.fouten.length > 0 && (
            <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm">
              {resultaat.fouten.map((f, i) => (
                <li key={i}>
                  <span className="font-medium">{f.naam}</span>: {f.detail}
                </li>
              ))}
            </ul>
          )}
        </Melding>
      )}

      {gefilterd.length === 0 ? (
        <Card className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <p className="text-sm text-muted">Geen analyses gevonden met deze filters.</p>
          <Button variant="secondary" size="sm" onClick={() => setFilters(DEFAULT_FILTERS)}>
            Filters wissen
          </Button>
        </Card>
      ) : (
        <>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[37rem] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-faint">
                    <th className="w-10 px-4 py-3">
                      {paginaSelecteerbaar.length > 0 && (
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-accent"
                          aria-label="Selecteer alle analyses op deze pagina"
                          checked={alleOpPagina}
                          disabled={bezig !== null}
                          ref={(el) => {
                            if (el) el.indeterminate = enkeleOpPagina && !alleOpPagina;
                          }}
                          onChange={togglePagina}
                        />
                      )}
                    </th>
                    <th className="px-4 py-3 font-medium">Naam</th>
                    <th className="px-4 py-3 font-medium">Bron</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 font-medium">Bijgewerkt</th>
                  </tr>
                </thead>
                <tbody>
                  {lijst.map((p) => (
                    <tr
                      key={p.id}
                      className="group border-b border-line/60 last:border-0 transition-colors hover:bg-surface"
                    >
                      <td className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          className="h-4 w-4 accent-accent"
                          aria-label={`Selecteer ${p.naam || p.id}`}
                          checked={selectie.has(p.id)}
                          disabled={bezig !== null || !isDeletable(p.state)}
                          title={
                            isDeletable(p.state)
                              ? undefined
                              : "Kan niet verwijderd worden tijdens een lopende analyse"
                          }
                          onChange={() => toggle(p.id)}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link href={`/projecten/${pathSegment(p.id)}`} className="block">
                          <span className="font-medium text-ink group-hover:text-link">
                            {p.naam || p.id}
                          </span>
                          <span className="mt-0.5 block font-mono text-xs text-faint">{p.id}</span>
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-muted">
                        <span className="text-xs">{bronnenSamenvatting(p.bronnen)}</span>
                      </td>
                      <td className="px-4 py-3">
                        <StateBadge state={p.state} />
                        {p.scope === "act2" && (
                          <span className="ml-1.5 text-xs text-faint" title="Afgerond zonder activiteit 3">
                            act. 2
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted">{formatDatum(p.updated)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Pagination
            page={huidige}
            totalPages={totalPages}
            total={total}
            pageSize={PAGE_SIZE}
            onPage={setPage}
          />
        </>
      )}
    </div>
  );
}
