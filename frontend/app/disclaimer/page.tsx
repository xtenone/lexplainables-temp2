import { Suspense } from "react";
import { AuthFrame } from "@/components/auth/AuthFrame";
import { DisclaimerClient } from "@/components/auth/DisclaimerClient";
import { isDisclaimerGeaccepteerd } from "@/lib/authCookies";

export const metadata = { title: "Testomgeving · Wetsanalyse" };

/** De BLOKKERENDE variant: hierheen stuurt de edge-gate je vóórdat je de app in mag. Een gate is een
 *  pagina — er is nog niets om overheen te leggen — en hij draagt daarom hetzelfde kader als het
 *  inlogscherm waar je net vandaan komt.
 *
 *  Ben je al akkoord en klik je de teststrip in de werkplek aan, dan onderschept
 *  `app/@modal/(.)disclaimer` dit pad en opent dezelfde tekst als dialog over de werkplek. */
export default async function DisclaimerPagina() {
  // Geen redirect als het akkoord er al is: de strip in de werkplek linkt hierheen, dus de pagina
  // moet ook als leesversie bereikbaar blijven. De stand bepaalt alleen of er een akkoordknop staat.
  const alGeaccepteerd = await isDisclaimerGeaccepteerd();

  return (
    <AuthFrame
      breed
      titel="Voordat je begint"
      onderschrift="Lees dit even door. Het gaat over wat deze omgeving wel en niet is, en wat dat betekent voor het werk dat je hier doet."
    >
      {/* useSearchParams (callbackUrl) vereist een Suspense-grens bij het prerenderen. */}
      <Suspense fallback={null}>
        <DisclaimerClient alGeaccepteerd={alGeaccepteerd} />
      </Suspense>
    </AuthFrame>
  );
}
