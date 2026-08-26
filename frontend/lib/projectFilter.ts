import type { DashboardUpdate } from "./types";
import { distinctBwbIds } from "./bronnen";
import { statusBucket, type StatusBucket } from "./states";

export type SortKey = "bijgewerkt-desc" | "bijgewerkt-asc" | "naam" | "status";
export type StatusFilter = "alle" | StatusBucket;

export interface ProjectFilters {
  q: string;
  status: StatusFilter;
  wet: string; // "alle" of een bwbId
  sort: SortKey;
}

export const DEFAULT_FILTERS: ProjectFilters = {
  q: "",
  status: "alle",
  wet: "alle",
  sort: "bijgewerkt-desc",
};

export function filtersActief(f: ProjectFilters): boolean {
  return f.q.trim() !== "" || f.status !== "alle" || f.wet !== "alle";
}

// Aandacht-eerst: lopend/review boven, dan fout, dan klaar.
const STATUS_RANK: Record<StatusBucket, number> = { lopend: 0, review: 0, fout: 1, klaar: 2 };

/** Unieke BWB-id's over alle bronnen, gesorteerd — voor de wet-dropdown. */
export function distinctWetten(items: DashboardUpdate[]): string[] {
  return distinctBwbIds(items.map((u) => u.bronnen));
}

export function filterEnSorteer(items: DashboardUpdate[], f: ProjectFilters): DashboardUpdate[] {
  const q = f.q.trim().toLowerCase();
  const arr = items.filter((u) => {
    if (f.status !== "alle" && statusBucket(u.state, u.error) !== f.status) return false;
    if (f.wet !== "alle" && !(u.bronnen || []).some((b) => (b.bwbId || "") === f.wet)) return false;
    if (q) {
      const bronTekst = (u.bronnen || []).map((b) => `${b.bwbId || ""} ${b.artikel}`).join(" ");
      const hooi = `${u.naam} ${u.id} ${bronTekst}`.toLowerCase();
      if (!hooi.includes(q)) return false;
    }
    return true;
  });

  arr.sort((a, b) => {
    switch (f.sort) {
      case "naam":
        return (a.naam || a.id).localeCompare(b.naam || b.id, "nl");
      case "bijgewerkt-asc":
        return (a.updated || "").localeCompare(b.updated || "");
      case "status": {
        const r =
          STATUS_RANK[statusBucket(a.state, a.error)] - STATUS_RANK[statusBucket(b.state, b.error)];
        return r !== 0 ? r : (b.updated || "").localeCompare(a.updated || "");
      }
      case "bijgewerkt-desc":
      default:
        return (b.updated || "").localeCompare(a.updated || "");
    }
  });
  return arr;
}

export interface Paginering<T> {
  items: T[];
  page: number; // geclampt op [1, totalPages]
  totalPages: number;
  total: number;
}

export function paginate<T>(arr: T[], page: number, pageSize: number): Paginering<T> {
  const total = arr.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const veilig = Math.min(Math.max(1, page), totalPages);
  const start = (veilig - 1) * pageSize;
  return { items: arr.slice(start, start + pageSize), page: veilig, totalPages, total };
}
