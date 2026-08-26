"use client";

import Link from "next/link";

import { KleurStrip } from "@/components/annotaties/KleurStrip";
import { BevestigKnop } from "@/components/ui/BevestigKnop";
import { DOCUMENT_STATUS_LABEL, DOCUMENT_STATUS_STYLE } from "@/lib/annotatie";
import { naamVan, vindplaatsLabel } from "@/lib/annotatieOverzicht";
import type { DocumentSamenvatting } from "@/lib/types";

/** "3 dagen geleden" — genoeg om te zien wat blijft liggen, zonder valse precisie. */
function geleden(iso?: string | null): string {
  if (!iso) return "onbekend";
  const ms = Date.now() - Date.parse(iso);
  if (Number.isNaN(ms)) return "onbekend";
  const dagen = Math.floor(ms / 86_400_000);
  if (dagen >= 1) return dagen === 1 ? "gisteren" : `${dagen} dagen geleden`;
  const uren = Math.floor(ms / 3_600_000);
  if (uren >= 1) return `${uren} uur geleden`;
  return "zojuist";
}

const AANDACHT_STIJL: Record<string, string> = {
  rood: "bg-aandacht-rood-bg text-aandacht-rood-tekst border-aandacht-rood-rand",
  geel: "bg-aandacht-geel-bg text-aandacht-geel-tekst border-aandacht-geel-rand",
};

export function AnnotatieKaart({
  doc,
  onVerwijder,
}: {
  doc: DocumentSamenvatting;
  onVerwijder: (slug: string) => void;
}) {
  const beoordeeld = doc.aantal_elementen - doc.te_beoordelen;
  return (
    <article className="flex flex-col gap-3 rounded-button border border-line bg-paper p-4 transition-shadow hover:shadow-kaart">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {/* De hele kaart aanklikbaar maken zou de knoppen eronder onbereikbaar maken voor het
              toetsenbord; daarom is de titel de link. */}
          <h3 className="truncate font-display text-sm font-semibold text-lint">
            <Link href={`/annotaties/${doc.slug}`} className="focus-ring rounded hover:underline">
              {naamVan(doc)}
            </Link>
          </h3>
          <p className="text-xs text-muted">
            {vindplaatsLabel(doc)} · {doc.bwbId}
          </p>
        </div>
        <span
          className={`inline-flex shrink-0 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${DOCUMENT_STATUS_STYLE[doc.status]}`}
        >
          {DOCUMENT_STATUS_LABEL[doc.status]}
        </span>
      </div>

      <KleurStrip perKlasse={doc.per_klasse} />

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
        <span>
          {doc.aantal_elementen === 0
            ? "nog geen markeringen"
            : `${beoordeeld} van ${doc.aantal_elementen} beoordeeld`}
        </span>
        {(["rood", "geel"] as const).map((niveau) =>
          (doc.per_aandacht?.[niveau] ?? 0) > 0 ? (
            <span
              key={niveau}
              className={`inline-flex items-center rounded-full border px-1.5 py-0.5 ${AANDACHT_STIJL[niveau]}`}
            >
              {doc.per_aandacht[niveau]} {niveau}
            </span>
          ) : null,
        )}
        <span>bijgewerkt {geleden(doc.updated)}</span>
        {doc.laatste_model && <span className="font-mono text-[0.65rem]">{doc.laatste_model}</span>}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={`/annotaties/${doc.slug}`}
          className="focus-ring inline-flex min-h-[24px] items-center rounded-full border border-line px-2.5 py-0.5 text-[11px] font-medium text-lint transition-colors hover:bg-surface coarse:min-h-[44px]"
        >
          Openen
        </Link>
        {/* Verwijderen kan hier omdat dit overzicht de wezen zichtbaar maakt: annotaties waarvan het
            gesprek allang weg is. Twee klikken, zoals overal in deze app. Andersom laten we het
            gesprek juist met rust: dat blijft staan met een kaart die zegt dat de annotatie weg is. */}
        <BevestigKnop
          bevestigTekst="Verwijderen?"
          onBevestig={() => onVerwijder(doc.slug)}
          titel="Het gesprek waarin deze annotatie is gemaakt blijft staan; de kaart daarin meldt dan dat hij verwijderd is."
          ariaLabel={`Annotatie ${naamVan(doc)} ${vindplaatsLabel(doc)} verwijderen`}
          className="focus-ring inline-flex min-h-[24px] items-center rounded-full border border-line px-2.5 py-0.5 text-[11px] font-medium text-muted transition-colors hover:bg-surface hover:text-ink coarse:min-h-[44px]"
          bevestigClassName="border-fout/40 bg-fout/10 text-fout"
        >
          Verwijderen
        </BevestigKnop>
      </div>
    </article>
  );
}
