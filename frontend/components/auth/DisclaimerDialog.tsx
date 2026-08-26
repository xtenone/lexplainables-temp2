"use client";

import { useRouter } from "next/navigation";

import { DisclaimerClient } from "@/components/auth/DisclaimerClient";
import { Dialog } from "@/components/ui/Dialog";

/** De voorwaarden zoals je ze vanuit de werkplek naleest: een dialog over de chat heen, net als de
 *  instellingen. Sluiten met `router.back()` — de intercepting route heeft een history-entry
 *  toegevoegd, dus je landt terug op precies de plek in je gesprek waar je was.
 *
 *  De blokkerende variant (nog geen akkoord) is de volle pagina `app/disclaimer/page.tsx`: dan stuurt
 *  de edge-gate je hierheen vóórdat de app rendert en is er niets om overheen te leggen. Beide tonen
 *  dezelfde `DisclaimerClient`, zodat de tekst maar op één plek bestaat. */
export function DisclaimerDialog({ alGeaccepteerd }: { alGeaccepteerd: boolean }) {
  const router = useRouter();
  // Eén sluitweg voor het kruisje, de achtergrondklik, Escape én de knop onderin. Die laatste was een
  // link naar `/` en liet de dialoog juist openstaan.
  const sluit = () => router.back();

  return (
    // Ook hier volgt de hoogte de inhoud: de voorwaarden zijn een half scherm tekst, geen venster
    // van 42rem.
    <Dialog label="Voorwaarden testomgeving" variant="compact" onSluit={sluit}>
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5 pt-[max(0.875rem,env(safe-area-inset-top))]">
        <h2 className="font-display text-base font-semibold text-lint">Voordat je begint</h2>
        <button
          type="button"
          onClick={sluit}
          aria-label="Voorwaarden sluiten"
          className="focus-ring -mr-1 rounded-kaart p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
        <DisclaimerClient alGeaccepteerd={alGeaccepteerd} onSluiten={sluit} />
      </div>
    </Dialog>
  );
}
