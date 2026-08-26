"use client";

import { Button } from "@/components/ui/Button";

/** Eenvoudige client-side paginering (Vorige/Volgende + indicator). Verbergt zich bij ≤ 1 pagina. */
export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  if (totalPages <= 1) return null;
  const van = (page - 1) * pageSize + 1;
  const tot = Math.min(page * pageSize, total);

  return (
    // Wrappend: bij vier cijfers ("1–20 van 1240") past de telling naast Vorige/Volgende niet meer
    // op een telefoon, en dan liep de rij over de rand.
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2 pt-3">
      <span className="text-xs text-muted">
        {van}–{tot} van {total}
      </span>
      <div className="flex items-center gap-2">
        <Button variant="secondary" size="sm" onClick={() => onPage(page - 1)} disabled={page <= 1}>
          Vorige
        </Button>
        <span className="whitespace-nowrap text-xs text-muted">
          pagina {page} / {totalPages}
        </span>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => onPage(page + 1)}
          disabled={page >= totalPages}
        >
          Volgende
        </Button>
      </div>
    </div>
  );
}
