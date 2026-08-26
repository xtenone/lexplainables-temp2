"use client";

import { useSyncExternalStore } from "react";

/** Vanaf welke breedte het artefact naast de chat past in plaats van eroverheen.
 *
 *  Onder deze grens blijft er na de gesprekssidebar (17rem) en het artefact te weinig chat over om
 *  nog bruikbaar te zijn; dan is de inschuivende sheet beter. Gelijk aan Tailwinds `xl`. */
const BREED = "(min-width: 1280px)";

function abonneer(opWijziging: () => void): () => void {
  const mq = window.matchMedia(BREED);
  mq.addEventListener("change", opWijziging);
  return () => mq.removeEventListener("change", opWijziging);
}

/** Is het scherm breed genoeg voor de kolom-indeling?
 *
 *  Via `useSyncExternalStore` en niet via `useState` + effect: `matchMedia` ís externe state, en zo
 *  leest React de waarde tijdens het renderen in plaats van er één frame achteraan te lopen. Op de
 *  server bestaat `matchMedia` niet — daar is het antwoord `false`. Dat is hier onschuldig: het
 *  artefact opent pas na een interactie, dus de eerste render toont het toch niet.
 */
export function useBreedScherm(): boolean {
  return useSyncExternalStore(
    abonneer,
    () => window.matchMedia(BREED).matches,
    () => false,
  );
}
