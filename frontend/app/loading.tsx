import { Skeleton } from "@/components/ui/Skeleton";

// Suspense-fallback tijdens de server-render. De vorm volgt het kader dat erna verschijnt (een
// gecentreerde kaart), zodat er niets verspringt zodra de pagina er is.
export default function Laden() {
  return (
    <div className="flex min-h-screen min-h-[100dvh] items-center justify-center bg-surface px-4 py-10" aria-busy="true">
      <span className="sr-only">Laden…</span>
      <div className="w-full max-w-sm">
        <Skeleton className="mx-auto mb-6 h-[3.75rem] w-[13rem]" />
        <div className="rounded-vorm border border-line bg-paper p-6 shadow-kaart sm:p-8">
          <Skeleton className="h-7 w-40" />
          <Skeleton className="mt-3 h-4 w-full" />
          <Skeleton className="mt-6 h-10 w-full" />
          <Skeleton className="mt-3 h-10 w-full" />
        </div>
      </div>
    </div>
  );
}
