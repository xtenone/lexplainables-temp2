/** @type {import('next').NextConfig} */

// Conservatieve security-headers op alle routes. HSTS bewust NIET hier: TLS wordt door NPM
// getermineerd, dat zet Strict-Transport-Security. De CSP staat inline scripts/styles toe
// omdat Next.js (App Router) en Tailwind die nodig hebben; fonts worden via next/font lokaal
// geserveerd ('self'). SSE en /api lopen same-origin, dus connect-src 'self' volstaat.
//
// BEKENDE AFWEGING: `script-src 'unsafe-inline'` verzwakt de XSS-mitigatie van de CSP. Dit is een
// bewuste keuze (Next.js injecteert inline hydration-scripts). De hardening-route is een
// nonce-gebaseerde CSP (nonce per request via de middleware, doorgegeven aan Next); dat is een
// aparte, grotere wijziging en staat als toekomstwerk genoteerd. Overige lagen (React-escaping,
// href-schema-guards in lib/url.ts, X-Content-Type-Options, frame-ancestors 'none') blijven de
// eerste verdediging.
const csp = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data:",
  "font-src 'self'",
  "connect-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
