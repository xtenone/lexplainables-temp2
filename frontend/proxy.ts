// Route-bescherming: bewaakt élke pagina + BFF-route (behalve login/setup/auth en assets) via de
// edge-veilige authConfig. De `authorized`-callback (auth.config.ts) bepaalt toegang en de rol-gate
// op /beheer en /api/admin.
//
// Next 16 hernoemde de "middleware"-conventie naar "proxy" (zelfde edge-hook, andere bestandsnaam +
// default-export). We exporteren de NextAuth-`auth`-functie expliciet als default zodat de
// Turbopack-build 'm als proxy-functie herkent (de gedestructureerde named export werd niet gezien).

import NextAuth from "next-auth";
import { authConfig } from "./auth.config";

const { auth } = NextAuth(authConfig);

export default auth;

export const config = {
  // Sluit Auth.js' eigen routes, Next-interne paden en statische bestanden uit.
  //
  // Twee dingen in dit patroon zijn er met opzet, want de kopieerbare variant die overal rondgaat
  // laat een gat vallen. De bestandsextensies staan **verankerd op het einde** (`$`): zonder dat
  // matcht `.*\.png` élk pad waar ".png" ergens in voorkomt, dus ook `/api/gesprekken/abc.png`, en
  // dan loopt dat verzoek buiten de sessie-, rol- en Origin-controle om. En `/api/` is expliciet
  // uitgezonderd van die bestandstak: onder de BFF staan geen statische bestanden, en een
  // dynamische route-parameter mág eruitzien als een bestandsnaam. De routehandlers doen ieder hun
  // eigen controle, maar deze laag hoort juist het vangnet te zijn voor de keer dat iemand dat
  // vergeet.
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|manifest.webmanifest|(?!api/).*\\.(?:svg|png|jpg|jpeg|gif|ico|webmanifest)$).*)",
  ],
};
