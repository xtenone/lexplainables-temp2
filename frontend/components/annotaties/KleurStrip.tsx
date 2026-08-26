"use client";

import { kleurstrip } from "@/lib/annotatieOverzicht";
import { JAS_KLASSEN, jasStyle } from "@/lib/jas";

/** De JAS-verdeling van een annotatie als gekleurde balk.
 *
 *  Waar Claude's artifacts een thumbnail tonen, kan hier iets staan dat écht iets zegt: hoe de
 *  markeringen over de dertien klassen verdeeld zijn. Twee documenten naast elkaar zijn zo te
 *  vergelijken zonder ze te openen — voorwaarde-zwaar leest anders dan subject-zwaar.
 *
 *  De strip is decoratie voor een schermlezer (de aantallen staan als tekst op de kaart), maar het
 *  `title`-attribuut geeft de verdeling wel bij het aanwijzen. */
export function KleurStrip({ perKlasse }: { perKlasse: Record<string, number> }) {
  const delen = kleurstrip(perKlasse, JAS_KLASSEN);
  if (delen.length === 0) {
    return <div className="h-1.5 rounded-full bg-surface" aria-hidden />;
  }
  return (
    <div className="flex h-1.5 gap-px overflow-hidden rounded-full" aria-hidden>
      {delen.map((d) => (
        <span
          key={d.klasse}
          title={`${d.klasse}: ${d.aantal}`}
          style={{ flexGrow: d.aantal }}
          // Alleen de achtergrond uit de JAS-kleur; tekst en rand zijn hier niet aan de orde.
          className={`${jasStyle(d.klasse).split(" ")[0]} block h-full`}
        />
      ))}
    </div>
  );
}
