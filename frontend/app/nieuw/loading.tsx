import { Skeleton, SkeletonCard } from "@/components/ui/Skeleton";

// Suspense-fallback voor het nieuwe-analyse-formulier tijdens de server-render.
export default function Laden() {
  return (
    <div className="animate-rise mx-auto max-w-2xl space-y-6" aria-busy="true">
      <span className="sr-only">Formulier laden…</span>
      <div className="space-y-2">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-4 w-full max-w-prose" />
      </div>
      <SkeletonCard regels={6} />
    </div>
  );
}
