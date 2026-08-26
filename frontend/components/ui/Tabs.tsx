"use client";

import { useId, useRef, type ReactNode } from "react";

export interface TabDef {
  /** Stabiele sleutel; ook gebruikt voor de aria-id's. */
  key: string;
  label: string;
  content: ReactNode;
}

// Toegankelijke tablist in Rijkshuisstijl: lintblauw onderlijn-indicator op de actieve tab.
// Beide panelen blijven gemount; het inactieve krijgt `hidden` (display:none) i.p.v. te unmounten,
// zodat de print-/PDF-stylesheet ze allebei kan tonen. Pijltjestoetsen verplaatsen de focus.
export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (key: string) => void;
}) {
  const base = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = e.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
    const nextKey = tabs[next].key;
    onChange(nextKey);
    tabRefs.current[nextKey]?.focus();
  }

  return (
    <div>
      <div role="tablist" aria-label="Fasen" className="flex gap-1 border-b border-line print:hidden">
        {tabs.map((t, i) => {
          const selected = t.key === active;
          return (
            <button
              key={t.key}
              ref={(el) => {
                tabRefs.current[t.key] = el;
              }}
              role="tab"
              id={`${base}-tab-${t.key}`}
              aria-selected={selected}
              aria-controls={`${base}-panel-${t.key}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(t.key)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-px min-h-[44px] border-b-2 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint ${
                selected
                  ? "border-lint text-lint"
                  : "border-transparent text-muted hover:text-lint"
              }`}
            >
              {t.label}
            </button>
          );
        })}
      </div>
      {tabs.map((t) => (
        <div
          key={t.key}
          role="tabpanel"
          id={`${base}-panel-${t.key}`}
          aria-labelledby={`${base}-tab-${t.key}`}
          data-tabpanel
          hidden={t.key !== active}
          className="pt-6"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}
