"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { DashboardUpdate, JobSummary } from "./types";

/** Beginstand uit de SSR-lijst; de aggregate-SSE verrijkt/overschrijft dit binnen enkele seconden. */
export function summaryNaarUpdate(s: JobSummary): DashboardUpdate {
  return {
    id: s.id,
    naam: s.naam,
    bronnen: s.bronnen ?? [],
    state: s.state,
    scope: s.scope ?? "volledig",
    current_activiteit: null,
    current_ronde: 0,
    current_fase: s.current_fase ?? null,
    current_fase_sinds: null,
    created: s.updated,
    updated: s.updated,
    model_profile: s.model_profile ?? "",
    tokens_in: s.tokens_in ?? 0,
    tokens_out: s.tokens_out ?? 0,
    error: null,
  };
}

/** Eén aggregate-SSE-stream over álle projecten van de client. Seedt uit de SSR-lijst en houdt de
 *  momentopnamen live bij via `data:`- (gewijzigd/nieuw project) en `removed`-events. Gedeeld door de
 *  home-lijst en het dashboard, zodat beide live lopen zonder een tweede mechanisme. De browser
 *  herverbindt zelf na de ~10-min servercap; vandaar één stabiele EventSource per mount. */
export function useProjectenStream(initieel: JobSummary[]) {
  const [items, setItems] = useState<Map<string, DashboardUpdate>>(
    () => new Map(initieel.map((s) => [s.id, summaryNaarUpdate(s)])),
  );
  const [verbonden, setVerbonden] = useState(false);

  // Ids die de gebruiker zojuist lokaal (optimistisch) verwijderde. Zolang de server-read (`initieel`)
  // ze nog teruggeeft, mag de SSR-re-add hieronder ze NIET opnieuw invoegen — anders "herrijst" een
  // net-verwijderde rij bij een focus-/visibility-refresh terwijl de server nog niet is bijgetrokken.
  const verwijderdRef = useRef<Set<string>>(new Set());

  /** Verwijder rijen direct uit de lijst (optimistisch, naast de SSE-`removed`-bevestiging), zodat een
   *  geslaagde bulk-delete meteen zichtbaar is — ook als de aggregate-SSE net down is. */
  const verwijderLokaal = useCallback((ids: string[]) => {
    for (const id of ids) verwijderdRef.current.add(id);
    setItems((prev) => {
      const m = new Map(prev);
      for (const id of ids) m.delete(id);
      return m;
    });
  }, []);

  // Voeg rijen toe wanneer een verse SSR-snapshot binnenkomt (na een `router.refresh()` of een
  // focus-refresh): een net aangemaakte analyse verschijnt zo meteen, ook als de SSE-poll nog niet
  // is binnengekomen. De `useState`-initializer draait maar één keer, dus zónder dit zou een refresh
  // de lijst niet bijwerken. Alleen ONTBREKENDE rijen worden toegevoegd — bestaande rijen blijven van
  // de (rijkere, live) SSE-status, zodat we de fase-/voortgangsvelden niet met de coarse summary
  // overschrijven.
  useEffect(() => {
    if (initieel.length === 0) return;
    const aanwezig = new Set(initieel.map((s) => s.id));
    // Server heeft de verwijdering ingehaald (id niet meer in de snapshot) → guard opheffen.
    for (const id of verwijderdRef.current) {
      if (!aanwezig.has(id)) verwijderdRef.current.delete(id);
    }
    setItems((prev) => {
      const ontbrekend = initieel.filter(
        (s) => !prev.has(s.id) && !verwijderdRef.current.has(s.id),
      );
      if (ontbrekend.length === 0) return prev;
      const m = new Map(prev);
      for (const s of ontbrekend) m.set(s.id, summaryNaarUpdate(s));
      return m;
    });
  }, [initieel]);

  useEffect(() => {
    const es = new EventSource("/api/projects/events");
    es.onopen = () => setVerbonden(true);
    es.onmessage = (e) => {
      try {
        const u = JSON.parse(e.data) as DashboardUpdate;
        setItems((prev) => new Map(prev).set(u.id, u));
      } catch {
        /* niet-JSON keepalive/regel — negeren */
      }
    };
    es.addEventListener("removed", (e) => {
      try {
        const { id } = JSON.parse((e as MessageEvent).data) as { id: string };
        setItems((prev) => {
          const m = new Map(prev);
          m.delete(id);
          return m;
        });
      } catch {
        /* negeren */
      }
    });
    es.onerror = () => setVerbonden(false); // browser herverbindt automatisch
    return () => es.close();
  }, []);

  return { items, verbonden, verwijderLokaal };
}
