"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button, LinkButton } from "@/components/ui/Button";
import { Melding } from "@/components/ui/Melding";
import { accepteerDisclaimer, isApiError } from "@/lib/api";
import { veiligPad } from "@/lib/url";

// Twee standen. Zonder akkoord (de gate stuurde je hierheen) staat er een knop; mét akkoord is dit
// een leespagina die je via de strip bovenaan altijd kunt terugvinden.
//
// `onSluiten` onderscheidt de twee schillen. Als dialoog (vanuit de werkplek) hoort de afsluitknop
// hetzelfde te doen als het kruisje: één stap terug in de historie. Er stond een link naar `/`, en
// dat sluit een intercepting-route-modal juist NIET — het modal-slot houdt zijn toestand vast bij een
// soft navigation, en `/` leidt ook nog door naar `/workbench`. Je hield de popup én kreeg er een
// history-entry bij, waarna het kruisje (`router.back()`) je terugbracht náár de voorwaarden.
export function DisclaimerClient({
  alGeaccepteerd,
  onSluiten,
}: {
  alGeaccepteerd: boolean;
  /** Meegeven in de dialoogschil; weglaten op de volle pagina, die gewoon wegnavigeert. */
  onSluiten?: () => void;
}) {
  const params = useSearchParams();
  const [fout, setFout] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);

  async function onAkkoord() {
    setFout(null);
    setBezig(true);
    try {
      await accepteerDisclaimer();
      // Harde navigatie (zie LoginClient.tsx): consistent met de andere post-auth-overgangen, en
      // voorkomt elke twijfel over een client-router die nog in de war is van de aanmeldstap
      // hiervoor.
      window.location.href = veiligPad(params.get("callbackUrl"), window.location.origin);
    } catch (e) {
      setFout(isApiError(e) ? e.detail : (e as Error).message);
      setBezig(false);
    }
  }

  return (
    <div className="space-y-4">
      {fout && <Melding type="fout">{fout}</Melding>}

      <Melding type="waarschuwing" titel="Testomgeving, geen productie">
        <p className="mt-1 text-sm">
          Deze omgeving is een <strong>proof of concept</strong>. Er wordt actief aan ontwikkeld;
          beschikbaarheid en stabiliteit zijn niet gegarandeerd.
        </p>
      </Melding>

      <Melding type="waarschuwing" titel="Geen garantie op behoud van analyses">
        <p className="mt-1 text-sm">
          Analyses kunnen <strong>zonder waarschuwing vooraf verwijderd worden of verloren gaan</strong>.
          Bewaar een lokale kopie van elk rapport dat je wilt behouden.
        </p>
      </Melding>

      <Melding type="waarschuwing" titel="Geen garantie op een eindproduct">
        <p className="mt-1 text-sm">
          Wat je hier ziet is een tussenstand. De uiteindelijke toepassing kan er
          <strong> heel anders uitzien</strong> — of er komt nooit een eindproduct.
        </p>
      </Melding>

      {alGeaccepteerd ? (
        onSluiten ? (
          <Button type="button" onClick={onSluiten} className="w-full sm:w-auto">
            Sluiten
          </Button>
        ) : (
          <LinkButton href="/" className="w-full sm:w-auto">
            Terug naar de werkplek
          </LinkButton>
        )
      ) : (
        <Button type="button" onClick={onAkkoord} disabled={bezig} className="w-full sm:w-auto">
          {bezig ? "Bezig…" : "Begrepen — doorgaan"}
        </Button>
      )}
    </div>
  );
}
