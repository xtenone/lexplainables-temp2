"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  getOngelezenAantal,
  listBerichten,
  markeerAllesGelezen,
} from "@/lib/api";
import type { BerichtOut, BerichtType } from "@/lib/types";
import { BerichtBadge } from "@/components/ui/BerichtBadge";
import { Popover } from "@/components/ui/Popover";
import { Skeleton } from "@/components/ui/Skeleton";
import { Markdown } from "@/components/werkplek/Markdown";
import { Tag } from "@/components/ui/Badge";

const TYPE_BALK: Record<BerichtType, string> = {
  info:         "bg-info",
  update:       "bg-succes",
  waarschuwing: "bg-waarschuwing",
  kritiek:      "bg-fout",
};

function BerichtItem({ bericht }: { bericht: BerichtOut }) {
  const datum = new Date(bericht.gepubliceerd_op ?? bericht.created).toLocaleDateString("nl-NL", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div
      className={`relative flex gap-3 border-b border-line px-4 py-3 last:border-0 ${
        bericht.gelezen ? "bg-paper" : "bg-surface"
      }`}
    >
      {!bericht.gelezen && (
        <span
          aria-hidden
          className={`absolute left-0 top-0 h-full w-1 rounded-l-sm ${TYPE_BALK[bericht.type as BerichtType]}`}
        />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <BerichtBadge type={bericht.type as BerichtType} />
          {bericht.versie && <Tag>{bericht.versie}</Tag>}
        </div>
        <p className="mt-1 text-sm font-semibold text-ink">{bericht.titel}</p>
        <div className="mt-1">
          <Markdown tekst={bericht.inhoud} />
        </div>
        <p className="mt-1.5 text-xs text-faint">{datum}</p>
      </div>
    </div>
  );
}

export function BerichtenPanel({ positie, containerClassName }: { positie?: string; containerClassName?: string } = {}) {
  const [ongelezen, setOngelezen] = useState(0);
  const [berichten, setBerichten] = useState<BerichtOut[] | null>(null);
  const [laden, setLaden] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  const laadAantal = useCallback(async () => {
    try {
      const { aantal } = await getOngelezenAantal();
      setOngelezen(aantal);
    } catch {
      // Badge stil laten staan bij een netwerk-hapering.
    }
  }, []);

  useEffect(() => {
    // De setState zit ín de async callback, dus pas ná het await — geen synchrone cascading
    // render. De regel kan daar niet doorheen kijken.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void laadAantal();
    const id = setInterval(() => void laadAantal(), 60_000);
    return () => clearInterval(id);
  }, [laadAantal]);

  const onOpen = useCallback(async () => {
    setLaden(true);
    try {
      // listBerichten gebruikt ?ongelezen=true — server filtert al.
      const items = await listBerichten();
      setBerichten(items);
      if (items.length > 0) {
        await markeerAllesGelezen().catch(() => {});
        setOngelezen(0);
        setBerichten(items.map((b) => ({ ...b, gelezen: true })));
      }
    } catch {
      // Panel tonen wat er al staat bij een fout.
    } finally {
      setLaden(false);
    }
  }, []);

  const badgeLabel = ongelezen > 99 ? "99+" : String(ongelezen);

  return (
    <Popover
      positie={positie}
      containerClassName={containerClassName}
      // Zelfde vormgeving als het gebruikersmenu onderin de sidebar (rounded-kaart, shadow-kaart).
      // De breedte komt uit `positie` (inset-x-3), niet uit een vaste maat: zo volgt het paneel de
      // kolom waarin het hangt en kan het per definitie niet buiten beeld vallen.
      className="max-h-[min(480px,70vh)] overflow-y-auto rounded-kaart border border-line bg-paper shadow-kaart"
      ariaLabel="Berichten"
      onClose={() => triggerRef.current?.focus()}
      trigger={(open, toggle) => (
        <button
          ref={triggerRef}
          type="button"
          aria-label="Berichten"
          aria-expanded={open}
          onClick={() => {
            toggle();
            if (!open) void onOpen();
          }}
          className="relative ml-1 flex h-10 w-10 shrink-0 items-center justify-center rounded-button coarse:h-11 coarse:w-11 text-muted transition-colors hover:text-lint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          {/* Bell-icoon */}
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
            <path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {/* Ongelezen-badge */}
          {ongelezen > 0 && (
            <span
              aria-hidden
              className="absolute right-1 top-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-fout px-0.5 text-[0.6rem] font-bold leading-none text-paper"
            >
              {badgeLabel}
            </span>
          )}
        </button>
      )}
    >
      <div className="border-b border-line px-4 py-2.5">
        <p className="text-sm font-semibold text-ink">Berichten</p>
      </div>
      {laden && (
        <div className="space-y-3 p-4">
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-2/3" />
        </div>
      )}
      {!laden && berichten !== null && berichten.length === 0 && (
        <p className="px-4 py-4 text-sm text-muted">Geen nieuwe berichten.</p>
      )}
      {!laden && berichten !== null && berichten.length > 0 && (
        <div>
          {berichten.map((b) => (
            <BerichtItem key={b.id} bericht={b} />
          ))}
        </div>
      )}
      {!laden && (
        <div className="border-t border-line px-4 py-2">
          <Link href="/instellingen/berichten" className="text-xs text-lint hover:underline">
            Alle berichten bekijken →
          </Link>
        </div>
      )}
    </Popover>
  );
}
