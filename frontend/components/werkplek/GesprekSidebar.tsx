"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { signOut, useSession } from "next-auth/react";

import { BerichtenPanel } from "@/components/BerichtenPanel";
import { FeedbackDialoog } from "@/components/FeedbackDialoog";
import { GesprekLijst } from "@/components/werkplek/GesprekLijst";
import { wisDisclaimer } from "@/lib/api";
import type { GesprekSamenvatting } from "@/lib/types";

/** Wis het disclaimer-akkoord en log dan pas uit: zonder dat overleeft de sessiecookie een logout
 *  binnen dezelfde browsersessie en ziet de volgende gebruiker op een gedeelde machine de
 *  waarschuwing niet. */
async function uitloggen(): Promise<void> {
  await wisDisclaimer();
  await signOut({ callbackUrl: "/login" });
}

interface Props {
  gesprekken: GesprekSamenvatting[];
  activeId?: string | null;
  onNieuw: () => void;
  onOpen: (id: string) => void;
  onHernoem: (id: string, titel: string) => void;
  onVerwijder: (id: string) => void;
  /** Eerste gesprekken-fetch loopt nog: sidebar toont skeleton-rijen. */
  laden?: boolean;
  /** Alleen mobiel: sluitknop voor de drawer. */
  onSluit?: () => void;
}

/** De linker-sidebar van de werkplek: bovenin het Belastingdienst-logo, daaronder de chatgeschiedenis,
 *  onderin het instellingen-/gebruikersblok. Vult de volle hoogte; alleen de gesprekslijst scrollt. */
export function GesprekSidebar({
  gesprekken,
  activeId,
  onNieuw,
  onOpen,
  onHernoem,
  onVerwijder,
  laden,
  onSluit,
}: Props) {
  const { data: session } = useSession();
  const pad = usePathname();
  const annotatiesActief = pad?.startsWith("/annotaties") ?? false;
  const [menuOpen, setMenuOpen] = useState(false);
  const [feedbackOpen, setFeedbackOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const isBeheerder = session?.user?.role === "beheerder";
  const naam = session?.user?.userid ?? session?.user?.email ?? "";

  // Sluit de instellingen-popover bij Escape of een klik buiten het blok.
  useEffect(() => {
    if (!menuOpen) return;
    const opBuiten = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false);
    };
    const opEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("mousedown", opBuiten);
    window.addEventListener("keydown", opEsc);
    return () => {
      document.removeEventListener("mousedown", opBuiten);
      window.removeEventListener("keydown", opEsc);
    };
  }, [menuOpen]);

  return (
    <div className="flex h-full flex-col bg-surface">
      {/* Logo + berichten + sluitknop (mobiel). `relative`: het berichtenpaneel hangt aan deze rij,
          niet aan de bel, zodat het net als het gebruikersmenu onderin de volle sidebarbreedte
          volgt (inset-x-3) en nooit buiten de kolom valt. */}
      <div className="relative flex items-center justify-between px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <Link href="/" aria-label="Belastingdienst, naar startpagina" className="block py-1">
          <Image
            src="/belastingdienst-logo.svg"
            alt="Belastingdienst"
            width={275}
            height={125}
            unoptimized
            priority
            className="block h-auto w-[8.5rem]"
          />
        </Link>
        <div className="flex items-center">
          <BerichtenPanel positie="inset-x-3 top-full mt-1" containerClassName="static" />
          {onSluit && (
            <button
              type="button"
              onClick={onSluit}
              aria-label="Menu sluiten"
              className="focus-ring rounded-kaart p-2 text-muted transition-colors hover:bg-surface hover:text-ink lg:hidden"
            >
              {/* Hetzelfde kruisje als de dialogen; een tekst-✕ weegt anders en lijnt anders uit. */}
              <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
                <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
              </svg>
            </button>
          )}
        </div>
      </div>

      <div className="px-3 pb-2 pt-3">
        <button
          type="button"
          onClick={onNieuw}
          className="flex min-h-[44px] w-full items-center gap-2 rounded-kaart border border-line bg-paper px-3 py-2.5 text-sm font-medium text-lint shadow-zacht transition-colors hover:bg-white hover:shadow-kaart focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden>
            <path d="M12 5v14M5 12h14" />
          </svg>
          Nieuw gesprek
        </button>
      </div>

      {/* Navigatie, bewust lichter dan de knop erboven: dat is een actie, dit is een plek. De
          annotaties leven los van de gesprekken — een annotatie overleeft het gesprek waarin hij
          gemaakt is, en moet dus ook zonder dat gesprek te vinden zijn. */}
      <div className="px-3 pb-1">
        <Link
          href="/annotaties"
          onClick={onSluit}
          aria-current={annotatiesActief ? "page" : undefined}
          className={`focus-ring flex min-h-[36px] items-center gap-2 rounded-lg px-2.5 py-2 text-sm transition-colors coarse:min-h-[44px] ${
            annotatiesActief ? "bg-lint/10 font-medium text-lint" : "text-ink hover:bg-paper"
          }`}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
            <path d="M4 5h16M4 12h10M4 19h7" />
            <circle cx="18" cy="17" r="3" />
          </svg>
          Annotaties
        </Link>
      </div>

      {/* Chatgeschiedenis (scrollt) */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        <p className="px-2 pb-1 pt-2 text-[0.65rem] font-semibold uppercase tracking-wide text-faint">
          Geschiedenis
        </p>
        <GesprekLijst
          gesprekken={gesprekken}
          activeId={activeId}
          onOpen={onOpen}
          onHernoem={onHernoem}
          onVerwijder={onVerwijder}
          laden={laden}
        />
      </div>

      {/* Instellingen + gebruiker (onderin) */}
      <div ref={menuRef} className="relative border-t border-line px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2">
        {menuOpen && (
          <div className="absolute inset-x-3 bottom-full mb-1 overflow-hidden rounded-kaart border border-line bg-paper shadow-kaart">
            <Link
              href="/instellingen/account"
              className="block px-3 py-2.5 text-sm text-ink transition-colors hover:bg-surface"
              onClick={() => setMenuOpen(false)}
            >
              Account &amp; instellingen
            </Link>
            {isBeheerder && (
              <Link
                href="/instellingen/beheer/modelprofielen"
                className="block px-3 py-2.5 text-sm text-ink transition-colors hover:bg-surface"
                onClick={() => setMenuOpen(false)}
              >
                Beheer
              </Link>
            )}
            <button
              type="button"
              onClick={() => {
                setMenuOpen(false);
                setFeedbackOpen(true);
              }}
              className="block w-full px-3 py-2.5 text-left text-sm text-ink transition-colors hover:bg-surface"
            >
              Feedback geven
            </button>
            <button
              type="button"
              onClick={() => void uitloggen()}
              className="block w-full px-3 py-2.5 text-left text-sm text-fout transition-colors hover:bg-fout/10"
            >
              Uitloggen
            </button>
          </div>
        )}
        <button
          type="button"
          onClick={() => setMenuOpen((o) => !o)}
          aria-expanded={menuOpen}
          className="flex min-h-[44px] w-full items-center gap-2.5 rounded-kaart px-2 py-2 text-left transition-colors hover:bg-surface-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-lint text-xs font-semibold text-paper">
            {(naam || "?").slice(0, 2).toUpperCase()}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-medium text-ink">{naam || "Gebruiker"}</span>
            <span className="block truncate text-[0.65rem] text-faint">
              {isBeheerder ? "Beheerder" : "Analist"} · instellingen
            </span>
          </span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="shrink-0 text-muted" aria-hidden>
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
      </div>

      {feedbackOpen && <FeedbackDialoog onSluit={() => setFeedbackOpen(false)} />}
    </div>
  );
}
