"use client";

// Toegankelijke combobox met autocomplete (WAI-ARIA 1.2), zelfbouw op de bestaande
// veld-primitives — gebruikt voor de artikelkeuze in het analyseformulier. De component
// dwingt zelf níét af dat de waarde in de lijst staat (dat is een form-check), zodat hij
// ook bruikbaar blijft wanneer de lijst (nog) leeg is.

import { useEffect, useId, useRef, useState } from "react";
import { inputBase } from "./Field";
import { filterArtikelen, telTreffers } from "@/lib/artikelFilter";
import type { ArtikelChoice } from "@/lib/types";

const MAX_OPTIES = 50;

interface ComboboxProps {
  value: string;
  onChange: (tekst: string) => void;
  onSelect?: (item: ArtikelChoice) => void;
  items: ArtikelChoice[];
  placeholder?: string;
  className?: string;
}

export function Combobox({ value, onChange, onSelect, items, placeholder, className }: ComboboxProps) {
  const listboxId = useId();
  const [open, setOpen] = useState(false);
  const [actief, setActief] = useState(0);
  const lijstRef = useRef<HTMLUListElement>(null);

  const opties = filterArtikelen(items, value, MAX_OPTIES);
  const totaal = telTreffers(items, value);
  const rest = totaal - opties.length;

  // Actieve index binnen de (na typen gekrompen) lijst houden.
  useEffect(() => {
    if (actief >= opties.length) setActief(0);
  }, [opties.length, actief]);

  // Het actieve item zichtbaar houden bij toetsenbordnavigatie.
  useEffect(() => {
    if (!open) return;
    lijstRef.current
      ?.querySelector(`[data-index="${actief}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [actief, open]);

  function kies(item: ArtikelChoice) {
    onChange(item.artikel);
    onSelect?.(item);
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const delta = e.key === "ArrowDown" ? 1 : -1;
      setActief((a) => Math.min(Math.max(a + delta, 0), Math.max(opties.length - 1, 0)));
    } else if (e.key === "Enter") {
      if (open && opties[actief]) {
        e.preventDefault(); // selectie, geen form-submit
        kies(opties[actief]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    } else if (e.key === "Tab") {
      setOpen(false); // getypte waarde blijft staan
    }
  }

  const optieId = (i: number) => `${listboxId}-optie-${i}`;

  return (
    <div className={`relative ${className ?? ""}`}>
      <input
        role="combobox"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={open && opties[actief] ? optieId(actief) : undefined}
        autoComplete="off"
        className={inputBase}
        value={value}
        placeholder={placeholder}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
          setActief(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
      />
      {open && opties.length > 0 && (
        <ul
          ref={lijstRef}
          id={listboxId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full min-w-56 overflow-y-auto rounded-field border border-line bg-paper py-1 shadow-lg"
        >
          {opties.map((item, i) => (
            <li
              key={`${item.artikel}-${i}`}
              id={optieId(i)}
              data-index={i}
              role="option"
              aria-selected={i === actief}
              className={`cursor-pointer px-3 py-2 text-sm ${i === actief ? "bg-lint/10" : ""}`}
              // onMouseDown + preventDefault: anders blurt de input vóór de click landt.
              onMouseDown={(e) => {
                e.preventDefault();
                kies(item);
              }}
              onMouseMove={() => setActief(i)}
            >
              <span className="font-medium text-ink">Art. {item.artikel}</span>
              {item.pad && <span className="ml-2 text-xs text-muted">{item.pad}</span>}
            </li>
          ))}
          {rest > 0 && (
            <li aria-hidden="true" className="px-3 py-2 text-xs text-faint">
              … nog {rest} artikel{rest === 1 ? "" : "en"} — typ verder om te verfijnen
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
