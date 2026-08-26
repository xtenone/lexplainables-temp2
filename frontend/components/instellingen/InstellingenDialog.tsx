"use client";

import { useRouter } from "next/navigation";
import { Dialog } from "@/components/ui/Dialog";
import type { TabKey } from "@/lib/instellingen";
import { InstellingenInhoud } from "./InstellingenInhoud";

/** Het instellingenvenster zoals je het vanuit de werkplek opent: een gecentreerde dialog over de
 *  chat heen. Sluiten gaat met `router.back()` — de intercepting route heeft een history-entry
 *  toegevoegd, dus daarmee land je terug op de werkplek zonder de pagina te herladen. */
export function InstellingenDialog({ actief, isBeheerder }: { actief: TabKey; isBeheerder: boolean }) {
  const router = useRouter();

  return (
    <Dialog label="Instellingen" variant="center" onSluit={() => router.back()}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5 pt-[max(0.875rem,env(safe-area-inset-top))]">
        <h2 className="font-display text-base font-semibold text-lint">Instellingen</h2>
        <button
          type="button"
          onClick={() => router.back()}
          aria-label="Instellingen sluiten"
          className="-mr-1 rounded-kaart p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <InstellingenInhoud actief={actief} isBeheerder={isBeheerder} vervangHistorie />
    </Dialog>
  );
}
