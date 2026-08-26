"use client";

import { usePathname } from "next/navigation";

/** Globale site-footer. Weggelaten op de assistent-/werkplek-pagina (`/workbench`): dat is een
 *  vol-hoogte, chat-first scherm (invoerbalk gepind onderaan) waar een footer alleen ruimte inneemt —
 *  zeker op mobiel. Op alle andere pagina's (normale documentflow) staat de footer gewoon onderaan. */
export function SiteFooter() {
  const pathname = usePathname();
  if (pathname === "/workbench") return null;

  return (
    <footer className="mx-auto max-w-6xl px-6 pb-10 pt-4 text-xs text-faint">
      <span className="font-medium text-muted">Belastingdienst</span> · Methode Wetsanalyse
      (Ausems, Bulles &amp; Lokin) · Juridisch Analyseschema · brongetrouw herleidbaar naar
      artikel, lid en bronreferentie.
    </footer>
  );
}
