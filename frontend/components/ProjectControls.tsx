"use client";

import { Input, Select } from "@/components/ui/Field";
import type { ProjectFilters } from "@/lib/projectFilter";

/** Gedeelde zoek-/filter-/sorteerbalk voor de home-lijst en het dashboard. */
export function ProjectControls({
  filters,
  onChange,
  wetten,
  showStatus = true,
}: {
  filters: ProjectFilters;
  onChange: (f: ProjectFilters) => void;
  wetten: string[];
  showStatus?: boolean;
}) {
  const set = <K extends keyof ProjectFilters>(k: K, v: ProjectFilters[K]) =>
    onChange({ ...filters, [k]: v });

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <Input
        type="search"
        value={filters.q}
        onChange={(e) => set("q", e.target.value)}
        placeholder="Zoek op naam, BWB-id of artikel…"
        aria-label="Zoeken"
        className="sm:min-w-[16rem] sm:flex-1"
      />
      {showStatus && (
        <Select
          value={filters.status}
          onChange={(e) => set("status", e.target.value as ProjectFilters["status"])}
          aria-label="Filter op status"
          className="sm:w-auto"
        >
          <option value="alle">Alle statussen</option>
          <option value="lopend">Lopend</option>
          <option value="review">Wacht op review</option>
          <option value="klaar">Klaar</option>
          <option value="fout">Fout</option>
        </Select>
      )}
      <Select
        value={filters.wet}
        onChange={(e) => set("wet", e.target.value)}
        aria-label="Filter op wet"
        className="sm:w-auto"
      >
        <option value="alle">Alle wetten</option>
        {wetten.map((w) => (
          <option key={w} value={w}>
            {w}
          </option>
        ))}
      </Select>
      <Select
        value={filters.sort}
        onChange={(e) => set("sort", e.target.value as ProjectFilters["sort"])}
        aria-label="Sorteren"
        className="sm:w-auto"
      >
        <option value="bijgewerkt-desc">Nieuwste eerst</option>
        <option value="bijgewerkt-asc">Oudste eerst</option>
        <option value="naam">Naam (A–Z)</option>
        <option value="status">Status</option>
      </Select>
    </div>
  );
}
