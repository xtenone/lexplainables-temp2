"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import { LinkButton } from "@/components/ui/Button";
import { wisDisclaimer } from "@/lib/api";

/** Wis het disclaimer-akkoord en log dan pas uit (gedeelde-machine-hygiëne). Zonder het wissen
 *  overleeft de disclaimer-sessiecookie een logout binnen dezelfde browsersessie en ziet de
 *  volgende gebruiker de waarschuwing niet. */
async function uitloggen(): Promise<void> {
  await wisDisclaimer();
  await signOut({ callbackUrl: "/login" });
}

type NavItem = { href: string; label: string; adminOnly?: boolean };

const ITEMS: NavItem[] = [
  { href: "/", label: "Projecten" },
  { href: "/workbench", label: "Assistent" },
  { href: "/account", label: "Account" },
  { href: "/beheer", label: "Beheer", adminOnly: true },
];

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function NavItem({
  href,
  label,
  active,
  onClick,
  block,
}: {
  href: string;
  label: string;
  active: boolean;
  onClick?: () => void;
  block?: boolean;
}) {
  return (
    <Link
      href={href}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={`relative px-3 py-3.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint ${
        block ? "w-full" : ""
      } ${active ? "text-lint" : "text-muted hover:text-lint"}`}
    >
      {label}
      {active && (
        <span aria-hidden className="absolute inset-x-3 bottom-0 h-[3px] rounded-full bg-lint" />
      )}
    </Link>
  );
}

export function SiteNav() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { data: session, status } = useSession();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Niet ingelogd (of nog aan het laden): geen navigatie tonen — de login-pagina staat los.
  if (status !== "authenticated" || !session?.user) return null;

  const isBeheerder = session.user.role === "beheerder";
  const items = ITEMS.filter((item) => !item.adminOnly || isBeheerder);

  return (
    <>
      {/* Desktop: nav inline, naast de applicatienaam in de navigatiebalk */}
      <nav className="hidden items-center gap-1 sm:flex">
        {items.map((item) => (
          <NavItem
            key={item.href}
            href={item.href}
            label={item.label}
            active={isActive(pathname, item.href)}
          />
        ))}
        <LinkButton href="/nieuw" size="sm" className="ml-2">
          Nieuwe analyse
        </LinkButton>
        <span className="ml-3 hidden max-w-[12rem] truncate text-xs text-faint lg:inline" title={session.user.email ?? ""}>
          {session.user.userid ?? session.user.email}
        </span>
        <button
          type="button"
          onClick={() => void uitloggen()}
          className="ml-2 rounded-button px-3 py-3.5 text-sm font-medium text-muted transition-colors hover:text-lint focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint"
        >
          Uitloggen
        </button>
      </nav>

      {/* Mobiel: hamburger-toggle */}
      <button
        type="button"
        aria-label={open ? "Menu sluiten" : "Menu openen"}
        aria-expanded={open}
        aria-controls="mobiel-menu"
        onClick={() => setOpen((v) => !v)}
        className="my-2 inline-flex shrink-0 items-center justify-center rounded-button border border-line p-2 text-lint transition-colors hover:bg-surface focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-lint sm:hidden"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
          {open ? (
            <>
              <line x1="6" y1="6" x2="18" y2="18" />
              <line x1="18" y1="6" x2="6" y2="18" />
            </>
          ) : (
            <>
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </>
          )}
        </svg>
      </button>

      {/* Mobiel: uitklappaneel onder de navigatiebalk */}
      {open && (
        <div
          id="mobiel-menu"
          className="absolute inset-x-0 top-full z-20 flex flex-col gap-1 border-b border-line bg-paper px-6 py-3 shadow-sm sm:hidden"
        >
          {items.map((item) => (
            <NavItem
              key={item.href}
              href={item.href}
              label={item.label}
              active={isActive(pathname, item.href)}
              onClick={() => setOpen(false)}
              block
            />
          ))}
          <LinkButton href="/nieuw" className="mt-1 w-full" onClick={() => setOpen(false)}>
            Nieuwe analyse
          </LinkButton>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              void uitloggen();
            }}
            className="mt-1 w-full rounded-button px-3 py-3 text-left text-sm font-medium text-muted transition-colors hover:text-lint"
          >
            Uitloggen ({session.user.userid ?? session.user.email})
          </button>
        </div>
      )}
    </>
  );
}
