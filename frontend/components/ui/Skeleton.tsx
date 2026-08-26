// Laad-skelet in de Rijkshuisstijl: een rustig pulserend blok in de surface/line-tokens (geen losse
// hex). Gebruikt door de route-`loading.tsx`-fallbacks zodat een navigatie meteen een zichtbare
// laadstaat toont i.p.v. een bevroren pagina.

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-line/60 ${className}`} aria-hidden="true" />;
}

/** Een platte kaart gevuld met enkele skelet-regels — de standaard laad-placeholder voor een blok. */
export function SkeletonCard({ regels = 3, className = "" }: { regels?: number; className?: string }) {
  return (
    <div className={`rounded-button border border-line bg-surface p-6 ${className}`}>
      <Skeleton className="h-5 w-1/3" />
      <div className="mt-4 space-y-2.5">
        {Array.from({ length: regels }).map((_, i) => (
          <Skeleton key={i} className={`h-3.5 ${i === regels - 1 ? "w-2/3" : "w-full"}`} />
        ))}
      </div>
    </div>
  );
}
