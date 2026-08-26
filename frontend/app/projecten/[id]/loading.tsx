import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";

// Suspense-fallback tijdens het server-side laden van een projectdetail. Toont meteen een skelet
// zodat de navigatie niet als een bevroren pagina aanvoelt.
export default function Laden() {
  return (
    <div className="animate-rise space-y-6" aria-busy="true">
      <span className="sr-only">Analyse laden…</span>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3">
          <Skeleton className="h-3 w-20" />
          <Skeleton className="h-7 w-64" />
          <div className="flex gap-2">
            <Skeleton className="h-5 w-24" />
            <Skeleton className="h-5 w-32" />
          </div>
        </div>
        <Skeleton className="h-12 w-32" />
      </div>
      <SkeletonCard regels={2} />
      <SkeletonCard regels={5} />
    </div>
  );
}
