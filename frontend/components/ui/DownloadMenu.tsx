"use client";

import { useEffect, useRef } from "react";

export type DownloadItem =
  | { type: "link"; label: string; href: string; primary?: boolean }
  | { type: "action"; label: string; onClick: () => void; primary?: boolean }
  | { type: "divider" };

// Klein download-menu in Rijkshuisstijl, dependency-vrij op basis van <details>/<summary>
// (native toetsenbord-toegankelijk). Sluit bij klik buiten het menu en bij Esc.
export function DownloadMenu({ items, label = "Download" }: { items: DownloadItem[]; label?: string }) {
  const ref = useRef<HTMLDetailsElement>(null);

  function close() {
    if (ref.current) ref.current.open = false;
  }

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current?.open && !ref.current.contains(e.target as Node)) close();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    document.addEventListener("click", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("click", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, []);

  const summary =
    "inline-flex min-h-[48px] cursor-pointer select-none items-center justify-center gap-2 whitespace-nowrap rounded-button border border-lint bg-paper px-5 py-2 text-sm font-medium text-lint transition-colors hover:bg-surface marker:content-none [&::-webkit-details-marker]:hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint";

  const rowBase =
    "block w-full rounded-field px-3 py-2 text-left text-sm transition-colors hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint";

  return (
    <details ref={ref} className="relative w-full sm:w-auto">
      <summary className={summary}>
        {label}
        <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true" className="opacity-70">
          <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <div className="absolute right-0 z-40 mt-2 w-64 max-w-[calc(100vw-3rem)] rounded-button border border-line bg-paper p-1 shadow-lg">
        {items.map((item, i) => {
          if (item.type === "divider") {
            return <div key={i} className="my-1 border-t border-line" />;
          }
          const cls = `${rowBase} ${item.primary ? "font-semibold text-lint" : "text-ink"}`;
          if (item.type === "link") {
            return (
              <a key={i} href={item.href} className={cls} onClick={close}>
                {item.label}
              </a>
            );
          }
          return (
            <button
              key={i}
              type="button"
              className={cls}
              onClick={() => {
                close();
                item.onClick();
              }}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </details>
  );
}
