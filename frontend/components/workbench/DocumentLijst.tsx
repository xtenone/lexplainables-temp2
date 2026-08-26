"use client";

import { Button } from "@/components/ui/Button";
import { DOCUMENT_STATUS_LABEL, DOCUMENT_STATUS_STYLE } from "@/lib/annotatie";
import type { DocumentSamenvatting, WetChoice } from "@/lib/types";

const badge =
  "inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium";

function korteDatum(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
}

interface Props {
  documenten: DocumentSamenvatting[];
  wetten: WetChoice[];
  activeSlug?: string;
  onOpen: (slug: string) => void;
  onNew: () => void;
  onVerwijder: (slug: string) => void;
}

/** Linker kolom van de workbench: al je annotatie-documenten, klik om te heropenen/verder te
 *  reviewen. De persistente staat (elementen + beslissingen) komt uit de api. */
export function DocumentLijst({ documenten, wetten, activeSlug, onOpen, onNew, onVerwijder }: Props) {
  const naam = (bwbId: string) => wetten.find((w) => w.bwbId === bwbId)?.naam || bwbId;
  const gesorteerd = [...documenten].sort((a, b) =>
    (b.updated ?? "").localeCompare(a.updated ?? ""),
  );

  return (
    <aside className="flex flex-col gap-3">
      <Button size="sm" onClick={onNew} className="w-full">
        + Nieuwe annotatie
      </Button>

      {gesorteerd.length === 0 ? (
        <p className="px-1 text-sm text-muted">Nog geen annotaties.</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {gesorteerd.map((d) => {
            const actief = d.slug === activeSlug;
            return (
              <li
                key={d.slug}
                className={`group rounded-xl border p-3 transition-colors ${
                  actief ? "border-lint bg-surface" : "border-line bg-paper hover:border-lint/50"
                }`}
              >
                <button
                  type="button"
                  onClick={() => onOpen(d.slug)}
                  className="block w-full text-left"
                >
                  <span className="text-sm font-medium text-ink">
                    {naam(d.bwbId)} — art. {d.artikel}
                    {d.lid ? ` lid ${d.lid}` : ""}
                  </span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className={`${badge} ${DOCUMENT_STATUS_STYLE[d.status]}`}>
                      {DOCUMENT_STATUS_LABEL[d.status]}
                    </span>
                    <span className="text-xs text-muted">{d.aantal_elementen} elementen</span>
                    {korteDatum(d.updated) && (
                      <span className="text-xs text-muted">· {korteDatum(d.updated)}</span>
                    )}
                  </span>
                </button>
                <div className="mt-2 text-right">
                  <button
                    type="button"
                    onClick={() => onVerwijder(d.slug)}
                    className="text-xs text-muted opacity-0 transition hover:text-fout focus:opacity-100 group-hover:opacity-100"
                  >
                    Verwijderen
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </aside>
  );
}
