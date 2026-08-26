"use client";

import { useRef, useState } from "react";

import { BevestigKnop } from "@/components/ui/BevestigKnop";
import { Skeleton } from "@/components/ui/Skeleton";
import type { GesprekSamenvatting } from "@/lib/types";

function korteDatum(iso?: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const nu = new Date();
  const zelfdeDag = d.toDateString() === nu.toDateString();
  return zelfdeDag
    ? d.toLocaleTimeString("nl-NL", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("nl-NL", { day: "numeric", month: "short" });
}

interface Props {
  gesprekken: GesprekSamenvatting[];
  activeId?: string | null;
  onOpen: (id: string) => void;
  onHernoem: (id: string, titel: string) => void;
  onVerwijder: (id: string) => void;
  /** Eerste fetch loopt nog: toon skeleton-rijen i.p.v. de lege-staat. */
  laden?: boolean;
}

/** De chatgeschiedenis in de sidebar: klik om een gesprek te heropenen, hover voor hernoemen/verwijderen. */
export function GesprekLijst({ gesprekken, activeId, onOpen, onHernoem, onVerwijder, laden }: Props) {
  if (gesprekken.length === 0) {
    if (laden) {
      return (
        <div className="flex flex-col gap-1 px-1 py-1" aria-hidden>
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      );
    }
    return <p className="px-2 py-3 text-xs text-muted">Nog geen gesprekken.</p>;
  }
  return (
    <ul className="flex flex-col gap-0.5">
      {gesprekken.map((g) => (
        <Rij
          key={g.id}
          gesprek={g}
          actief={g.id === activeId}
          onOpen={() => onOpen(g.id)}
          onHernoem={(titel) => onHernoem(g.id, titel)}
          onVerwijder={() => onVerwijder(g.id)}
        />
      ))}
    </ul>
  );
}

function Rij({
  gesprek,
  actief,
  onOpen,
  onHernoem,
  onVerwijder,
}: {
  gesprek: GesprekSamenvatting;
  actief: boolean;
  onOpen: () => void;
  onHernoem: (titel: string) => void;
  onVerwijder: () => void;
}) {
  const [bewerk, setBewerk] = useState(false);
  const [titel, setTitel] = useState(gesprek.titel);
  const label = gesprek.titel || "Nieuw gesprek";
  // `Enter` sluit de bewerk-modus (unmount van de input) → `onBlur` vuurt daarná óók: guard tegen 2× PATCH.
  const bewaardRef = useRef(false);

  function bewaar() {
    if (bewaardRef.current) return;
    bewaardRef.current = true;
    const schoon = titel.trim();
    if (schoon && schoon !== gesprek.titel) onHernoem(schoon);
    setBewerk(false);
  }

  if (bewerk) {
    return (
      <li className="px-1 py-0.5">
        <input
          autoFocus
          value={titel}
          onChange={(e) => setTitel(e.target.value)}
          onBlur={bewaar}
          onKeyDown={(e) => {
            if (e.key === "Enter") bewaar();
            if (e.key === "Escape") {
              setTitel(gesprek.titel);
              setBewerk(false);
            }
          }}
          className="w-full rounded-field border border-lint bg-paper px-2 py-1.5 text-sm text-ink focus:outline-none"
        />
      </li>
    );
  }

  return (
    <li
      className={`group relative flex items-center rounded-lg transition-colors ${
        actief ? "bg-lint/10" : "hover:bg-surface"
      }`}
    >
      <button
        type="button"
        onClick={onOpen}
        className="min-w-0 flex-1 px-2.5 py-2 text-left focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-lint"
      >
        <span className={`block truncate text-sm ${actief ? "font-medium text-lint" : "text-ink"}`}>
          {label}
        </span>
        <span className="mt-0.5 block text-[0.65rem] text-faint">
          {gesprek.aantal_berichten} berichten{korteDatum(gesprek.updated) ? ` · ${korteDatum(gesprek.updated)}` : ""}
        </span>
      </button>
      {/* Hover-acties: alleen op fijne pointers verborgen tot hover; op touch altijd zichtbaar. */}
      <div className="flex shrink-0 items-center gap-0.5 pr-1.5 opacity-100 transition-opacity lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100">
        <button
          type="button"
          onClick={() => {
            setTitel(gesprek.titel);
            bewaardRef.current = false;
            setBewerk(true);
          }}
          aria-label="Hernoemen"
          title="Hernoemen"
          className="rounded p-1 text-muted transition-colors hover:text-lint"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
        </button>
        <BevestigKnop
          onBevestig={onVerwijder}
          ariaLabel="Verwijderen"
          titel="Verwijderen"
          bevestigTekst="Verwijderen?"
          className="focus-ring rounded p-1 text-muted transition-colors hover:text-fout"
          bevestigClassName="px-1.5 text-[0.7rem] font-medium text-fout"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M3 6h18" />
            <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            <path d="M6 6v14a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V6" />
          </svg>
        </BevestigKnop>
      </div>
    </li>
  );
}
