import { Suspense } from "react";
import { DisclaimerClient } from "@/components/auth/DisclaimerClient";
import { isDisclaimerGeaccepteerd } from "@/lib/authCookies";

export const metadata = { title: "Testomgeving · Wetsanalyse" };

export default async function DisclaimerPagina() {
  // Geen redirect als het akkoord er al is: de strip bovenaan linkt hierheen, dus de pagina moet
  // ook als leesversie bereikbaar blijven. De stand bepaalt alleen of er een akkoordknop staat.
  const alGeaccepteerd = await isDisclaimerGeaccepteerd();

  return (
    <div className="animate-rise mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Voordat je begint</h1>
        <p className="mt-1 text-sm text-muted">
          Lees dit even door. Het gaat over wat deze omgeving wel en niet is, en wat dat betekent
          voor het werk dat je hier doet.
        </p>
      </div>
      {/* useSearchParams (callbackUrl) vereist een Suspense-grens bij het prerenderen. */}
      <Suspense fallback={null}>
        <DisclaimerClient alGeaccepteerd={alGeaccepteerd} />
      </Suspense>
    </div>
  );
}
