import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";

// Suspense-fallback voor het beheerscherm tijdens de server-render.
export default function Laden() {
  return (
    <div className="animate-rise space-y-6" aria-busy="true">
      <span className="sr-only">Beheer laden…</span>
      <Skeleton className="h-8 w-40" />
      <SkeletonCard regels={4} />
      <SkeletonCard regels={4} />
    </div>
  );
}
