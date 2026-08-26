import { Suspense } from "react";

import { DisclaimerDialog } from "@/components/auth/DisclaimerDialog";
import { isDisclaimerGeaccepteerd } from "@/lib/authCookies";

/** Onderschept `/disclaimer` bij navigatie vanuit de app (de teststrip in de werkplek): de
 *  voorwaarden openen dan als dialog over de werkplek in plaats van als eigen pagina. Bij een
 *  directe link, een refresh, of de redirect van de edge-gate valt Next terug op de volle pagina
 *  `app/disclaimer/page.tsx` — precies wat je wilt, want dán is het een blokkerende stap. */
export default async function DisclaimerOnderschept() {
  const alGeaccepteerd = await isDisclaimerGeaccepteerd();

  return (
    // useSearchParams (callbackUrl) in DisclaimerClient vereist een Suspense-grens.
    <Suspense fallback={null}>
      <DisclaimerDialog alGeaccepteerd={alGeaccepteerd} />
    </Suspense>
  );
}
