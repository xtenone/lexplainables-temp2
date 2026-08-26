"use client";

import { useEffect, useRef, useState } from "react";

/** Een knop die pas bij de tweede klik uitvoert.
 *
 *  Eén idioom voor "weet je het zeker" in de hele app. Het artefact deed dit al zo (× → "Wissen?");
 *  daarbuiten stond een native `window.confirm`, en dat is een systeemvenster in systeemtaal midden
 *  in een applicatie met een eigen vormtaal — bovendien niet te stylen, niet te testen en in sommige
 *  contexten geblokkeerd.
 *
 *  Scherp gezet ontwapent hij vanzelf: na een paar seconden, bij verlies van focus, of met Escape.
 *  Een knop die scherp blijft staan is een val — precies bij de handelingen waar dat het duurst is.
 */
export function BevestigKnop({
  children,
  bevestigTekst,
  onBevestig,
  ariaLabel,
  titel,
  className = "",
  bevestigClassName = "",
  disabled,
  wachtMs = 4000,
}: {
  /** Wat er in rust staat: tekst of een icoon. */
  children: React.ReactNode;
  /** Wat er staat zodra hij scherp staat, bv. "Verwijderen?". */
  bevestigTekst: string;
  onBevestig: () => void | Promise<void>;
  ariaLabel?: string;
  titel?: string;
  className?: string;
  /** Extra klassen voor de scherpe stand, zodat die er anders uitziet dan de rust-stand. */
  bevestigClassName?: string;
  disabled?: boolean;
  /** Hoe lang hij scherp blijft staan. */
  wachtMs?: number;
}) {
  const [scherp, setScherp] = useState(false);
  const knopRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!scherp) return;
    const id = window.setTimeout(() => setScherp(false), wachtMs);
    const opEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setScherp(false);
    };
    window.addEventListener("keydown", opEsc);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("keydown", opEsc);
    };
  }, [scherp, wachtMs]);

  return (
    <button
      ref={knopRef}
      type="button"
      disabled={disabled}
      aria-label={scherp ? bevestigTekst : ariaLabel}
      title={scherp ? bevestigTekst : titel}
      onBlur={() => setScherp(false)}
      onClick={(e) => {
        e.stopPropagation();
        if (!scherp) {
          setScherp(true);
          return;
        }
        setScherp(false);
        void onBevestig();
      }}
      className={scherp ? `${className} ${bevestigClassName}` : className}
    >
      {scherp ? bevestigTekst : children}
    </button>
  );
}
