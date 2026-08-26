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
    <div className="flex items-center justify-between gap-3 pt-3">
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
