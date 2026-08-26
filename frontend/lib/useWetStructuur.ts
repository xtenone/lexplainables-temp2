"use client";

// Client-hooks voor het analyseformulier: laad (en dedupliceer) de wetsstructuur per BWB-id
// voor de artikel-combobox. Meerdere bron-rijen op dezelfde wet delen één fetch via de
// module-level promise-cache; de echte caching (TTL) zit in de API. Bij een mis degradeert
// het formulier naar vrije tekst — de hook levert dan status "fout" en geen artikelen.

import { useEffect, useRef, useState } from "react";
import { getWetStructuur } from "./api";
import { isBwbId } from "./artikelFilter";
import type { WetStructuur } from "./types";

export type StructuurStatus = "geen" | "laden" | "geladen" | "fout";
export interface StructuurEntry {
  status: StructuurStatus;
  structuur: WetStructuur | null;
}

const cache = new Map<string, Promise<WetStructuur>>();

function laad(bwbId: string): Promise<WetStructuur> {
  let p = cache.get(bwbId);
  if (!p) {
    p = getWetStructuur(bwbId);
    // Fouten niet in de cache laten hangen: een volgende poging mag opnieuw proberen.
    p.catch(() => cache.delete(bwbId));
    cache.set(bwbId, p);
  }
  return p;
}

// Een dropdown-keuze uit de catalogus is meteen een complete BWB-id; alleen bij vrije-tekst-
// invoer dempt de debounce de lookups terwijl de gebruiker nog typt (BWBR0… matcht het
// id-patroon immers al vanaf het eerste cijfer).
const DEBOUNCE_MS = 400;

/**
 * Structuur-status per BWB-id voor alle bron-rijen tegelijk. `direct: true` (catalogus-
 * dropdown) laadt zonder debounce; anders wordt per id gewacht tot het typen stilvalt.
 */
export function useWetStructuren(
  bwbIds: string[],
  opties?: { direct?: boolean },
): Record<string, StructuurEntry> {
  const direct = opties?.direct ?? false;
  const [kaart, setKaart] = useState<Record<string, StructuurEntry>>({});
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const gestart = useRef(new Set<string>());
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const uniek = Array.from(new Set(bwbIds.map((id) => id.trim()).filter(isBwbId)));
  const sleutel = uniek.join("|");

  useEffect(() => {
    const timerKaart = timers.current;
    for (const id of uniek) {
      if (gestart.current.has(id) || timerKaart.has(id)) continue;
      const start = () => {
        timerKaart.delete(id);
        gestart.current.add(id);
        setKaart((k) => ({ ...k, [id]: { status: "laden", structuur: null } }));
        laad(id)
          .then((s) => mounted.current && setKaart((k) => ({ ...k, [id]: { status: "geladen", structuur: s } })))
          .catch(() => {
            gestart.current.delete(id); // een latere poging mag opnieuw proberen
            if (mounted.current) setKaart((k) => ({ ...k, [id]: { status: "fout", structuur: null } }));
          });
      };
      if (direct) start();
      else timerKaart.set(id, setTimeout(start, DEBOUNCE_MS));
    }
    // Cleanup ruimt alleen nog-niet-gestarte (debounce-)timers op: half getypte ids
    // vervallen, terwijl al lopende fetches gewoon in de kaart mogen landen.
    return () => {
      for (const t of timerKaart.values()) clearTimeout(t);
      timerKaart.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `sleutel` vat `uniek` samen
  }, [sleutel, direct]);

  return kaart;
}
