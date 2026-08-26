"use client";

// Route-niveau error boundary: vangt runtime-fouten in Client Components zodat de gebruiker
// een nette pagina ziet (met opnieuw-proberen) i.p.v. een lege crash.

import { useEffect } from "react";
import { Button } from "@/components/ui/Button";
import { Melding } from "@/components/ui/Melding";

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="mx-auto max-w-prose px-4 py-16">
      <Melding type="fout" titel="Er ging iets mis">
        <p className="mt-1 text-sm text-muted">
          De pagina kon niet correct worden geladen. Probeer het opnieuw; blijft het misgaan, ververs
          dan de pagina of ga terug naar het overzicht.
        </p>
        {error.digest && <p className="mt-2 font-mono text-xs text-faint">Referentie: {error.digest}</p>}
        <div className="mt-5 flex items-center gap-3">
          <Button onClick={() => reset()}>Opnieuw proberen</Button>
          <Button variant="secondary" onClick={() => (window.location.href = "/")}>
            Naar overzicht
          </Button>
        </div>
      </Melding>
    </div>
  );
}
