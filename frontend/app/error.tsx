"use client";

// Route-niveau error boundary: vangt runtime-fouten in Client Components zodat de gebruiker
// een nette pagina ziet (met opnieuw-proberen) i.p.v. een lege crash. Zelfde kader als de
// inlog-/disclaimerschermen — een foutpagina is geen reden om in een derde opmaak te belanden.

import { useEffect } from "react";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { Button } from "@/components/ui/Button";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <AuthFrame
      titel="Er ging iets mis"
      onderschrift="De pagina kon niet correct worden geladen. Probeer het opnieuw; blijft het misgaan, ververs dan de pagina of ga terug naar de werkplek."
    >
      {error.digest && (
        <p className="mb-4 font-mono text-xs text-faint">Referentie: {error.digest}</p>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button onClick={() => reset()} className="w-full sm:w-auto">
          Opnieuw proberen
        </Button>
        {/* Bewust een HARDE navigatie, geen router.push: we staan in een error boundary, dus de
            client-state is juist wat kapot is. Een soft navigatie houdt die state vast en kan
            meteen weer omvallen. */}
        {/* eslint-disable-next-line @next/next/no-location-assign-relative-destination */}
        <Button variant="secondary" className="w-full sm:w-auto" onClick={() => (window.location.href = "/workbench")}>
          Naar de werkplek
        </Button>
      </div>
    </AuthFrame>
  );
}
