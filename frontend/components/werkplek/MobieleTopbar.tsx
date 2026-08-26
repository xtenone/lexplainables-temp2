"use client";

import type { ReactNode } from "react";

/** De balk boven het hoofdgebied op smalle schermen: hamburger → sidebar-drawer, plus waar je bent.
 *
 *  Bestaat omdat `AppSidebar` onder `lg` een `hidden`-kolom is en zijn drawer alleen toont als de
 *  pagina hem opent. De werkplek deed dat wel, `/annotaties` en `/annotaties/[slug]` niet — en daar
 *  was op een half scherm dus géén sidebar en geen enkele manier om er een te krijgen: geen
 *  gesprekken, geen account, geen uitloggen. Eén component voor alle drie de schermen, zodat dat
 *  niet opnieuw uiteen kan lopen.
 */
export function MobieleTopbar({
  titel,
  onOpenSidebar,
  actie,
}: {
  /** Waar je bent. Wordt afgekapt; de sidebar draagt de volledige navigatie. */
  titel: string;
  onOpenSidebar: () => void;
  /** Optionele knop rechts (bijvoorbeeld "nieuw gesprek"). */
  actie?: ReactNode;
}) {
  return (
    <div className="flex shrink-0 items-center gap-2 border-b border-line px-3 py-2 pt-[max(0.5rem,env(safe-area-inset-top))] lg:hidden">
      <button
        type="button"
        onClick={onOpenSidebar}
        aria-label="Menu openen"
        className="focus-ring inline-flex items-center justify-center rounded-lg border border-line p-2 text-lint transition-colors hover:bg-surface"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
          <line x1="3" y1="6" x2="21" y2="6" />
          <line x1="3" y1="12" x2="21" y2="12" />
          <line x1="3" y1="18" x2="21" y2="18" />
        </svg>
      </button>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-lint">{titel}</span>
      {actie}
    </div>
  );
}
