"use client";

import type { Session } from "next-auth";
import { SessionProvider } from "next-auth/react";

// Maakt de Auth.js-sessie beschikbaar aan Client Components (SiteNav, account-UI) via useSession.
export function Providers({
  session,
  children,
}: {
  session: Session | null;
  children: React.ReactNode;
}) {
  return <SessionProvider session={session}>{children}</SessionProvider>;
}
