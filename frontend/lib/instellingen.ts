/** Tabdefinities van het instellingenvenster + de pure pad-helpers.
 *
 *  Bewust een eigen module **zonder** `"use client"`: zowel de server components (de volle pagina en
 *  de intercepting route, die de rolgate afdwingen) als de client-component roepen deze functies
 *  aan. Stonden ze in het client-bestand, dan faalt de server-aanroep met "Attempted to call
 *  tabUitPad() from the server but tabUitPad is on the client". */

export const INSTELLINGEN_TABS = [
  { key: "account", pad: "account", label: "Account", admin: false },
  { key: "beveiliging", pad: "beveiliging", label: "Beveiliging", admin: false },
  { key: "berichten", pad: "berichten", label: "Berichten", admin: false },
  { key: "modelprofielen", pad: "beheer/modelprofielen", label: "Modelprofielen", admin: true },
  { key: "gebruikers", pad: "beheer/gebruikers", label: "Gebruikers", admin: true },
  { key: "api-tokens", pad: "beheer/api-tokens", label: "API-tokens", admin: true },
  { key: "berichtenbeheer", pad: "beheer/berichten", label: "Berichten beheren", admin: true },
  { key: "feedback", pad: "beheer/feedback", label: "Feedback", admin: true },
] as const;

export type TabKey = (typeof INSTELLINGEN_TABS)[number]["key"];

/** Pad-segmenten (`["beheer","gebruikers"]`) → tabsleutel. Onbekend of leeg → `account`. */
export function tabUitPad(segmenten: string[] | undefined): TabKey {
  const pad = (segmenten ?? []).join("/");
  return INSTELLINGEN_TABS.find((t) => t.pad === pad)?.key ?? "account";
}

export function padVanTab(key: TabKey): string {
  const tab = INSTELLINGEN_TABS.find((t) => t.key === key);
  return `/instellingen/${tab ? tab.pad : "account"}`;
}

/** Is deze tab alleen voor beheerders? De beheer-tabs staan onder `beheer/`, zodat de rolgate in
 *  `auth.config.ts` één prefix-check blijft. */
export function isAdminTab(key: TabKey): boolean {
  return INSTELLINGEN_TABS.find((t) => t.key === key)?.admin ?? false;
}
