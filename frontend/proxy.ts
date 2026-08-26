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
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon.ico|manifest.webmanifest|.*\\.(?:svg|png|jpg|jpeg|gif|ico|webmanifest)).*)",
  ],
};
