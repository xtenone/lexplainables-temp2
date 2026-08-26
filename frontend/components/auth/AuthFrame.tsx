import Image from "next/image";
import type { ReactNode } from "react";

/** Het kader voor elk scherm buiten de app-schil: inloggen, 2FA, de eerste beheerder, de
 *  disclaimer-gate en de fout-/laadpagina's.
 *
 *  Eén gecentreerde kaart op een egaal vlak, met het logo erboven — dezelfde vormtaal als de dialogen
 *  in de werkplek (`rounded-vorm`, `bg-paper`, `shadow-kaart`). Daarmee is er nog maar één opmaak
 *  buiten de schil, in plaats van de oude documentflow met logobalk, navigatiebalk en footer. Die
 *  navigatie wees bovendien naar plekken die inmiddels ín de schil zitten.
 *
 *  Bewust géén namaak-werkplek op de achtergrond: een lege, vervaagde app achter glas leest als
 *  "hij is aan het laden" in plaats van als "je moet eerst inloggen".
 */
export function AuthFrame({
  titel,
  onderschrift,
  breed,
  children,
}: {
  titel: string;
  onderschrift?: ReactNode;
  /** Voor lange inhoud (de voorwaarden) een bredere kaart dan een formulier nodig heeft. */
  breed?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-screen min-h-[100dvh] flex-col items-center justify-center bg-surface px-4 py-10">
      <div className={`animate-rise w-full ${breed ? "max-w-2xl" : "max-w-sm"}`}>
        {/* Het lint (het blauwe blok) hoort op de horizontale middenas te staan, niet het logo als
            geheel. In de SVG (viewBox 275×125) is het lint 50 breed vanaf x=0, dus het hart ervan zit
            op 25/275 = 9,0909% van de logobreedte. Met `mx-auto` centreer je lint + woordmerk samen
            en staat het blok links van het midden.
            Vandaar: linkerrand op 50% zetten en dan 9,0909% van de eigen breedte terugschuiven — een
            percentage, zodat het klopt bij elke rendergrootte. Het logo is op de smalste schermen wat
            kleiner, anders loopt het na die verschuiving buiten de kaart. */}
        <Image
          src="/belastingdienst-logo.svg"
          alt="Belastingdienst"
          width={275}
          height={125}
          priority
          unoptimized
          className="relative left-1/2 mb-6 block h-auto w-[9.5rem] max-w-full -translate-x-[9.0909%] sm:w-[13rem]"
        />

        <div className="rounded-vorm border border-line bg-paper p-6 shadow-kaart sm:p-8">
          <h1 className="font-display text-2xl font-semibold text-lint">{titel}</h1>
          {onderschrift && <p className="mt-1 text-sm text-muted">{onderschrift}</p>}
          <div className="mt-6">{children}</div>
        </div>

        <p className="mt-6 text-center text-xs text-faint">
          Methode Wetsanalyse (Ausems, Bulles &amp; Lokin) · Juridisch Analyseschema
        </p>
      </div>
    </div>
  );
}
