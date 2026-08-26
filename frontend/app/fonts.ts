import { Fira_Sans, Fira_Mono } from "next/font/google";

// Rijkshuisstijl-typografie via een vrij alternatief: Fira Sans benadert Rijksoverheid
// Sans, Fira Mono dient voor tags/bronreferenties. Eén familie voor koppen én broodtekst.
// Gedeeld zodat zowel de root-layout als de global-error-boundary dezelfde (self-hosted,
// build-time gebundelde) font-instance gebruiken — geen dubbele subset.
export const sans = Fira_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-sans",
  display: "swap",
});

export const mono = Fira_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-mono",
  display: "swap",
});
