"use client";

// Vangt fouten die de root-layout zelf raken. Vervangt de hele document-boom, dus met eigen
// <html>/<body> en inline stijl (de app-styling is hier mogelijk niet geladen).

import { useEffect } from "react";

import { sans, mono } from "./fonts";

// Kleuren hardcoded op de huisstijl-tokens (uit app/globals.css) — de CSS-variabelen zijn hier
// niet gegarandeerd geladen. Fira via next/font (self-hosted, per-route geïnjecteerd; deze
// boundary kan de root-layout-font niet erven), met system-ui als fail-safe in de stack.
export default function GlobalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <html lang="nl">
      <body style={{ fontFamily: `${sans.style.fontFamily}, system-ui, sans-serif`, margin: 0, padding: "4rem 1rem", color: "#1A1A1A", background: "#FFFFFF" }}>
        <main style={{ maxWidth: "40rem", margin: "0 auto" }}>
          <h1 style={{ fontSize: "1.25rem" }}>Er ging iets mis</h1>
          <p style={{ color: "#4A5A6E" }}>
            De applicatie kon niet worden geladen. Probeer het opnieuw of ververs de pagina.
          </p>
          {error.digest && <p style={{ fontFamily: `${mono.style.fontFamily}, ui-monospace, monospace`, fontSize: "0.75rem", color: "#6B7685" }}>Referentie: {error.digest}</p>}
          <button
            onClick={() => reset()}
            style={{ marginTop: "1rem", padding: "0.5rem 1rem", borderRadius: "5px", border: "none", background: "#154273", color: "#FFFFFF", cursor: "pointer" }}
          >
            Opnieuw proberen
          </button>
        </main>
      </body>
    </html>
  );
}
