"use client";

import { useId, useRef, type ReactNode } from "react";

export interface TabDef {
  /** Stabiele sleutel; ook gebruikt voor de aria-id's. */
  key: string;
  label: string;
  content: ReactNode;
  /** Aantal openstaande items; > 0 toont een telbadge achter het label. De tab blijft toegankelijk
   *  benoemd via `label` — de badge zelf is `aria-hidden` en dus geen ruis voor schermlezers. */
  badge?: number;
}

// Toegankelijke tablist in Rijkshuisstijl: lintblauw onderlijn-indicator op de actieve tab.
// Beide panelen blijven gemount; het inactieve krijgt `hidden` (display:none) i.p.v. te unmounten,
// zodat de print-/PDF-stylesheet ze allebei kan tonen. Pijltjestoetsen verplaatsen de focus.
export function Tabs({
  tabs,
  active,
  onChange,
  orientation = "horizontal",
  lazy = false,
  label = "Fasen",
}: {
  tabs: TabDef[];
  active: string;
  onChange: (key: string) => void;
  /** `vertical` = tabkolom links (instellingen); `horizontal` = onderlijn-indicator (rapport). */
  orientation?: "horizontal" | "vertical";
  /** Alleen het actieve paneel renderen. Zet dit aan als panelen bij mount data ophalen — anders
   *  vuurt élk paneel zijn fetch zodra de tabs verschijnen. Uit (default) blijft alles gemount,
   *  wat de print-/PDF-stylesheet nodig heeft. */
  lazy?: boolean;
  label?: string;
}) {
  const base = useId();
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const verticaal = orientation === "vertical";

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const [vorige, volgende] = verticaal ? ["ArrowUp", "ArrowDown"] : ["ArrowLeft", "ArrowRight"];
    if (e.key !== volgende && e.key !== vorige) return;
    e.preventDefault();
    const next = e.key === volgende ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
    const nextKey = tabs[next].key;
    onChange(nextKey);
    tabRefs.current[nextKey]?.focus();
  }

  return (
    <div className={verticaal ? "flex min-h-0 flex-1 flex-col sm:flex-row" : undefined}>
      <div
        role="tablist"
        aria-label={label}
        aria-orientation={verticaal ? "vertical" : undefined}
        className={
          verticaal
            ? // Mobiel: horizontaal scrollbare rij bovenin; vanaf sm een kolom links.
              "flex shrink-0 gap-1 overflow-x-auto border-b border-line px-2 py-2 sm:w-56 sm:flex-col sm:overflow-x-visible sm:overflow-y-auto sm:border-b-0 sm:border-r sm:px-2 sm:py-3"
            : "flex gap-1 border-b border-line print:hidden"
        }
      >
        {tabs.map((t, i) => {
          const selected = t.key === active;
          const basis =
            "min-h-[44px] text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint";
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
              className={
                verticaal
                  ? `${basis} shrink-0 whitespace-nowrap rounded-kaart px-3 py-2 text-left sm:w-full ${
                      selected ? "bg-surface text-lint" : "text-muted hover:bg-surface hover:text-lint"
                    }`
                  : `${basis} -mb-px border-b-2 px-4 py-2 ${
                      selected ? "border-lint text-lint" : "border-transparent text-muted hover:text-lint"
                    }`
              }
            >
              {t.label}
              {t.badge !== undefined && t.badge > 0 && (
                <span
                  aria-hidden
                  className="ml-1.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-accent px-1 text-[0.6rem] font-bold leading-none text-paper"
                >
                  {t.badge > 99 ? "99+" : t.badge}
                </span>
              )}
            </button>
          );
        })}
      </div>
      {tabs.map((t) => {
        const selected = t.key === active;
        if (lazy && !selected) return null;
        return (
          <div
            key={t.key}
            role="tabpanel"
            id={`${base}-panel-${t.key}`}
            aria-labelledby={`${base}-tab-${t.key}`}
            data-tabpanel
            hidden={!selected}
            className={verticaal ? "min-h-0 flex-1 overflow-y-auto px-5 py-5" : "pt-6"}
          >
            {t.content}
          </div>
        );
      })}
    </div>
  );
}
