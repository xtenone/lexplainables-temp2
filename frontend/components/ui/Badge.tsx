import { jasStyle } from "@/lib/jas";

const base =
  "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium";

export function JasBadge({ klasse }: { klasse: string }) {
  // Lange JAS-labels mogen op smal scherm afbreken (anders perst de niet-krimpende badge de
  // naastliggende titel weg); op sm+ blijft het één regel.
  return (
    <span className={`${base} max-w-full break-words sm:whitespace-nowrap ${jasStyle(klasse)}`}>
      {klasse || "—"}
    </span>
  );
}

export function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex shrink-0 items-center rounded-field border border-line bg-surface px-2 py-0.5 font-mono text-xs text-muted">
      {children}
    </span>
  );
}
