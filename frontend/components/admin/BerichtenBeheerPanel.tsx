"use client";

import { BevestigKnop } from "@/components/ui/BevestigKnop";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card, Section } from "@/components/ui/Card";
import { BerichtBadge } from "@/components/ui/BerichtBadge";
import { Tag } from "@/components/ui/Badge";
import { Melding } from "@/components/ui/Melding";
import { Skeleton } from "@/components/ui/Skeleton";
import { Pagination } from "@/components/Pagination";
import { Markdown } from "@/components/werkplek/Markdown";
import { BerichtEditor } from "./BerichtEditor";
import {
  isApiError,
  listAlleBerichten,
  verwijderBericht,
  zetPublicatie,
} from "@/lib/api";
import type { AdminBerichtenPaginaOut, AdminBerichtOut, BerichtType } from "@/lib/types";

const PER_PAGINA = 20;

export function BerichtenBeheerPanel() {
  const [data, setData] = useState<AdminBerichtenPaginaOut | null>(null);
  const [pagina, setPagina] = useState(1);
  const [fout, setFout] = useState<string | null>(null);
  const [uitgeklapt, setUitgeklapt] = useState<Set<number>>(new Set());
  const [toonLijst, setToonLijst] = useState(false);
  // false = lijstweergave; null = nieuw bericht; AdminBerichtOut = bewerken
  const [editBericht, setEditBericht] = useState<AdminBerichtOut | null | false>(false);

  function toggleUitgeklapt(id: number) {
    setUitgeklapt((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const laad = useCallback(async (p: number) => {
    setFout(null);
    try {
      setData(await listAlleBerichten(p, PER_PAGINA));
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setData({ items: [], totaal: 0, pagina: p, per_pagina: PER_PAGINA });
    }
  }, []);

  function onToonBerichten() {
    setToonLijst(true);
    void laad(pagina);
  }

  function onPage(p: number) {
    setPagina(p);
    void laad(p);
  }

  async function onPublicatie(b: AdminBerichtOut) {
    try {
      await zetPublicatie(b.id, !b.gepubliceerd);
      await laad(pagina);
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  // Bevestigen doet de knop zelf (twee klikken), zoals overal in deze app.
  async function onVerwijder(b: AdminBerichtOut) {
    try {
      await verwijderBericht(b.id);
      await laad(pagina);
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  if (editBericht !== false) {
    return (
      <Section title={editBericht ? "Bericht bewerken" : "Nieuw bericht"}>
        <BerichtEditor
          bericht={editBericht}
          onCancel={() => setEditBericht(false)}
          onDone={() => { setEditBericht(false); setToonLijst(true); void laad(pagina); }}
        />
      </Section>
    );
  }

  return (
    <Section title="Berichten" subtitle="Release notes en aankondigingen voor analisten.">
      {fout && <Melding type="fout" compact className="mb-4">{fout}</Melding>}

      <ButtonRow className="mb-4">
        <Button onClick={() => setEditBericht(null)}>Nieuw bericht</Button>
        {!toonLijst && (
          <Button variant="secondary" onClick={onToonBerichten}>Toon berichten</Button>
        )}
      </ButtonRow>

      {toonLijst && data === null && (
        <div className="space-y-3">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {toonLijst && data !== null && data.items.length === 0 && (
        <p className="text-sm text-muted">Nog geen berichten.</p>
      )}

      {toonLijst && data !== null && data.items.length > 0 && (
        <div className="space-y-3">
          {data.items.map((b) => {
            const open = uitgeklapt.has(b.id);
            return (
              <Card key={b.id} className="overflow-hidden p-0">
                <button
                  type="button"
                  onClick={() => toggleUitgeklapt(b.id)}
                  className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left hover:bg-surface transition-colors"
                  aria-expanded={open}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <BerichtBadge type={b.type as BerichtType} />
                      {b.versie && <Tag>{b.versie}</Tag>}
                      <span
                        className={`text-xs font-medium ${
                          b.gepubliceerd ? "text-succes" : "text-muted"
                        }`}
                      >
                        {b.gepubliceerd ? "Gepubliceerd" : "Concept"}
                      </span>
                      <span className="text-xs text-faint">
                        {new Date(b.created).toLocaleDateString("nl-NL")}
                      </span>
                    </div>
                    <p className="mt-1 text-sm font-semibold text-ink">{b.titel}</p>
                  </div>
                  <span className={`mt-1 shrink-0 text-muted transition-transform ${open ? "rotate-180" : ""}`} aria-hidden>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="6 9 12 15 18 9" />
                    </svg>
                  </span>
                </button>
                {open && (
                  <div className="border-t border-line px-4 pb-4 pt-3">
                    <div className="text-sm">
                      <Markdown tekst={b.inhoud} />
                    </div>
                    <ButtonRow className="mt-3">
                      <Button size="sm" variant="secondary" onClick={() => setEditBericht(b)}>
                        Bewerken
                      </Button>
                      <Button size="sm" variant="secondary" onClick={() => void onPublicatie(b)}>
                        {b.gepubliceerd ? "Depubliceren" : "Publiceren"}
                      </Button>
                      <BevestigKnop
                        onBevestig={() => void onVerwijder(b)}
                        bevestigTekst="Definitief verwijderen?"
                        className="focus-ring inline-flex min-h-[40px] shrink-0 items-center justify-center rounded-field border border-fout px-3 text-sm font-medium text-fout transition coarse:min-h-[48px]"
                        bevestigClassName="bg-fout text-paper"
                      >
                        Verwijderen
                      </BevestigKnop>
                    </ButtonRow>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {toonLijst && data !== null && (
        <Pagination
          page={pagina}
          totalPages={Math.max(1, Math.ceil(data.totaal / PER_PAGINA))}
          total={data.totaal}
          pageSize={PER_PAGINA}
          onPage={onPage}
        />
      )}
    </Section>
  );
}
