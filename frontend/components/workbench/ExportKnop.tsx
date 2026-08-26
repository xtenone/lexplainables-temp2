"use client";

import { useState } from "react";

import { Popover } from "@/components/ui/Popover";
import { exporteerDocument, isApiError, type ExportFormaat } from "@/lib/api";

interface Props {
  slug: string;
  /** De letterlijke wettekst per lid (rauw, zonder nummer-voorvoegsel); gaat mee zodat het rapport
   *  de bron naast de tabel kan zetten. De api verzint hem niet — zonder leden blijft dat blok weg. */
  leden: { lid: string; tekst: string }[];
  onFout: (melding: string) => void;
}

const FORMATEN: { formaat: ExportFormaat; label: string; uitleg: string }[] = [
  { formaat: "pdf", label: "PDF", uitleg: "tabel in JAS-kleuren, met wettekst en volledig spoor" },
  { formaat: "csv", label: "CSV", uitleg: "één rij per markering, opent in Excel" },
  { formaat: "json", label: "JSON", uitleg: "alles, machineleesbaar" },
];

/** Download de annotatie — ook halverwege de review. Bewust geen statusdrempel: een concept
 *  exporteren is een normale handeling, en het bestand zegt zelf hoeveel er nog te beoordelen is.
 *
 *  Het paneel sluit na een geslaagde download doordat de Popover met een nieuwe `key` remount;
 *  de Popover geeft zijn eigen sluiter niet aan zijn kinderen door. */
export function ExportKnop({ slug, leden, onFout }: Props) {
  const [bezig, setBezig] = useState<ExportFormaat | null>(null);
  const [sleutel, setSleutel] = useState(0);

  async function download(formaat: ExportFormaat) {
    setBezig(formaat);
    try {
      await exporteerDocument(slug, formaat, leden);
      setSleutel((k) => k + 1);
    } catch (e) {
      onFout(isApiError(e) ? e.detail : "Exporteren is niet gelukt.");
    } finally {
      setBezig(null);
    }
  }

  return (
    <Popover
      key={sleutel}
      ariaLabel="Exporteren"
      className="w-64 rounded-lg border border-line bg-paper p-1 shadow-lg"
      trigger={(open, toggle) => (
        <button
          type="button"
          onClick={toggle}
          aria-expanded={open}
          disabled={bezig !== null}
          className="focus-ring inline-flex min-h-[24px] shrink-0 items-center gap-1 rounded-full border border-line px-2 py-0.5 text-[11px] font-medium text-muted transition-colors hover:bg-surface hover:text-ink disabled:opacity-60 coarse:min-h-[44px] coarse:px-3"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 3v12M7 11l5 5 5-5M4 21h16" />
          </svg>
          {bezig ? "Bezig…" : "Exporteren"}
        </button>
      )}
    >
      <ul className="space-y-0.5">
        {FORMATEN.map((f) => (
          <li key={f.formaat}>
            <button
              type="button"
              disabled={bezig !== null}
              onClick={() => void download(f.formaat)}
              className="focus-ring flex w-full flex-col items-start gap-0.5 rounded-md px-2.5 py-1.5 text-left transition-colors hover:bg-surface disabled:opacity-60"
            >
              <span className="text-sm font-medium text-ink">
                {bezig === f.formaat ? `${f.label} — bezig…` : f.label}
              </span>
              <span className="text-xs text-muted">{f.uitleg}</span>
            </button>
          </li>
        ))}
      </ul>
    </Popover>
  );
}
