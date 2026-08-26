"use client";

import { useState } from "react";

import { Vinkje } from "@/components/ui/Icoon";
import { alGemarkeerd } from "@/lib/annotatie";
import { jasStyle } from "@/lib/jas";
import { lidUitOffset, maakAnker, vindPositie, type LidRegel } from "@/lib/selectie";
import type { AnnotatieElement, OntbrekendItem } from "@/lib/types";

/** Wat de Critic nog mist, als werkvoorraad in plaats van als mededeling.
 *
 *  De Critic levert deze lijst nadat de herzieningslus is uitgewerkt: het is dus wat de annoteerder
 *  níét heeft opgelost. Meestal omdat er geen letterlijk fragment bij stond — en zonder fragment kan
 *  niemand het toevoegen, want elk element moet letterlijk in de wettekst staan.
 *
 *  Staat het fragment er wél bij en is het terug te vinden, dan is toevoegen één klik: het wordt jouw
 *  markering (`human_approved`), met een anker op de plek waar het gevonden is.
 *
 *  **Er is geen "wegleggen".** Dit is informatie, geen takenlijst: wat je toevoegt verdwijnt vanzelf
 *  uit de openstaande lijst, en waar je het niet mee eens bent laat je staan. Een wegklik-knop
 *  suggereerde een afhandeling die nergens werd vastgelegd — terwijl juist "Lex zag hier een
 *  Rechtssubject en ik vind van niet" een interpretatiekeuze is die je in het spoor zou willen
 *  terugvinden. Zolang dat spoor er niet is, is niets vastleggen eerlijker dan doen alsof.
 */
export function OntbrekendLijst({
  items,
  bron,
  regels,
  elementen,
  onToevoegen,
}: {
  items: OntbrekendItem[];
  /** De samengevoegde artikeltekst — hierin wordt het fragment opgezocht. */
  bron: string;
  /** De regels mét hun lidnummer, voor de lid-toewijzing van een toegevoegd item. */
  regels: LidRegel[];
  /** Wat er al ligt, om te herkennen wat inmiddels is gemarkeerd. */
  elementen: AnnotatieElement[];
  onToevoegen?: (invoer: {
    klasse: string; tekst: string; lid: string; toelichting: string;
    anker: ReturnType<typeof maakAnker>;
  }) => Promise<void>;
}) {
  const [bezig, setBezig] = useState<number | null>(null);

  const isKlaar = (item: OntbrekendItem) => alGemarkeerd(elementen, item.klasse, item.tekst ?? "");

  // Alles afgehandeld? Dan hoort hier niets meer te staan. Een blok met alleen vinkjes is ruis.
  const openstaand = items.filter((item) => !isKlaar(item)).length;
  if (openstaand === 0) return null;

  return (
    <div className="rounded-kaart border border-dashed border-line bg-surface p-3">
      <p className="text-xs font-medium text-muted">
        Mogelijk ontbrekend — Lex denkt dat dit er ook in zit ({openstaand})
      </p>

      <ul className="mt-2 space-y-2">
        {items.map((item, i) => {
          const fragment = (item.tekst ?? "").trim();
          const start = fragment ? vindPositie(bron, fragment, null, []) : -1;
          const klaar = isKlaar(item);
          const toevoegbaar = !!onToevoegen && start >= 0 && !klaar;

          return (
            // Zelfde vorm als een reviewkaart: het gaat om hetzelfde ding — een JAS-klasse met een
            // letterlijk fragment. Alleen de gestippelde rand om het blok markeert dat deze nog niet
            // in het document staan.
            <li key={i} className="rounded-kaart border border-line border-l-4 border-l-line bg-paper p-3">
              <span className={`inline-block rounded px-2 py-0.5 text-xs font-semibold ${jasStyle(item.klasse)}`}>
                {item.klasse}
              </span>

              {/* Het fragment krijgt dezelfde citaatvorm als op de reviewkaart, en wordt NIET afgekapt:
                  je moet het kunnen lezen om te kunnen besluiten of je het toevoegt. */}
              {fragment ? (
                <p className="mt-2 border-l-2 border-line pl-2.5 text-sm italic text-ink">“{fragment}”</p>
              ) : (
                <p className="mt-2 border-l-2 border-line pl-2.5 text-sm text-faint">
                  geen fragment aangewezen
                </p>
              )}

              {item.reden && <p className="mt-1.5 text-xs text-muted">{item.reden}</p>}

              {/* Drie situaties, drie boodschappen. Niets verzwijgen: kan het niet, zeg dan waarom. */}
              {fragment && start < 0 && (
                <p className="mt-1 text-xs text-aandacht-geel-tekst">
                  Dit fragment staat niet letterlijk in de opgehaalde tekst.
                </p>
              )}
              {!fragment && (
                <p className="mt-1 text-xs text-faint">
                  Selecteer het zelf in de tekst om het te markeren.
                </p>
              )}

              {/* Alleen renderen als er iets te tonen valt: zonder fragment is er geen knop en geen
                  vinkje, en een lege regel met marge oogt als een fout. */}
              {(klaar || toevoegbaar) && (
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  {klaar ? (
                    <span className="inline-flex items-center gap-1 text-xs text-succes">
                      <Vinkje /> inmiddels gemarkeerd
                    </span>
                  ) : (
                    <button
                      type="button"
                      disabled={bezig === i}
                      onClick={async () => {
                        setBezig(i);
                        try {
                          const lid = lidUitOffset(regels, start);
                          await onToevoegen!({
                            klasse: item.klasse,
                            tekst: fragment,
                            lid,
                            toelichting: "",
                            anker: maakAnker(bron, start, start + fragment.length, lid),
                          });
                        } finally {
                          setBezig(null);
                        }
                      }}
                      className="focus-ring inline-flex min-h-[24px] items-center rounded-lg bg-lint px-2.5 py-1 text-xs font-medium text-paper transition hover:bg-accent-soft coarse:min-h-[44px] disabled:opacity-50"
                    >
                      Toevoegen als {item.klasse}
                    </button>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
