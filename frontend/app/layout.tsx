import type { Metadata, Viewport } from "next";
import { auth } from "@/auth";
import { Providers } from "@/components/Providers";
import { sans, mono } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Wetsanalyse | Belastingdienst",
  description:
    "Gestructureerd, brongetrouw en traceerbaar duiden van Nederlandse wet- en regelgeving (JAS).",
  manifest: "/manifest.webmanifest",
  applicationName: "Wetsanalyse | Belastingdienst",
  appleWebApp: { capable: true, title: "Wetsanalyse", statusBarStyle: "default" },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon.svg", type: "image/svg+xml" },
      { url: "/favicon-16.png", sizes: "16x16", type: "image/png" },
      { url: "/favicon-32.png", sizes: "32x32", type: "image/png" },
      { url: "/favicon-48.png", sizes: "48x48", type: "image/png" },
      { url: "/favicon-192.png", sizes: "192x192", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
};

export const viewport: Viewport = {
  themeColor: "#154273",
  // Laat het schermtoetsenbord de layout-viewport verkleinen in plaats van eroverheen te schuiven.
  // De werkplek is een niet-scrollende schil van 100dvh met de invoerbalk onderaan gepind; zonder
  // dit kan het toetsenbord die balk afdekken. Chrome/Android honoreert dit; iOS Safari (nog) niet —
  // dáár is het niet met een regel CSS op te lossen en moet iemand met een toestel kijken.
  interactiveWidget: "resizes-content",
};

/** De layout is bewust kaal: er is geen globale chrome meer. Elk scherm draagt zijn eigen kader —
 *  ingelogd is dat de app-schil (`/workbench`, `/instellingen`), uitgelogd de gecentreerde kaart van
 *  `AuthFrame`. De oude logobalk + navigatiebalk + footer zijn weg: die navigatie wees naar plekken
 *  die inmiddels ín de schil zitten, en de kop verborg zichzelf toch al op de app-paden.
 *
 *  `modal` is het parallelle slot dat de intercepting routes vullen (app/@modal/**); dat staat
 *  buiten `{children}`, want een dialog hoort over de hele app heen te liggen. */
export default async function RootLayout({
  children,
  modal,
}: {
  children: React.ReactNode;
  modal: React.ReactNode;
}) {
  const session = await auth();
  return (
    <html lang="nl" className={`${sans.variable} ${mono.variable}`}>
      {/* `min-h-[100dvh]` en niet alleen `min-h-screen`: `100vh` is op mobiel de viewport ZONDER
          adresbalk, dus zolang die balk in beeld staat is de body hoger dan wat je ziet en kan het
          document zelf scrollen. Dan schuiven de testomgeving-strook en de topbar mee weg terwijl de
          app-schil eronder juist niet-scrollend bedoeld is. `100dvh` volgt de zichtbare hoogte, dus
          er blijft niets over om te scrollen. `min-h-screen` blijft ervóór staan als terugval voor
          browsers zonder dvh. */}
      <body className="min-h-screen min-h-[100dvh]">
        <Providers session={session}>
          {children}
          {modal}
        </Providers>
      </body>
    </html>
  );
}
