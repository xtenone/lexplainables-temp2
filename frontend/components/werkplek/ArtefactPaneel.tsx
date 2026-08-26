"use client";

import { ArtefactInhoud, type ArtefactInhoudProps } from "@/components/werkplek/ArtefactInhoud";
import { Dialog, type DialogVariant } from "@/components/ui/Dialog";

interface Props extends Omit<ArtefactInhoudProps, "onSluiten"> {
  /** `side` = inschuivende overlay (smal scherm), `kolom` = eigen kolom naast de chat (breed). */
  variant?: DialogVariant;
  onSluit: () => void;
}

/** De dialoogschil om het annotatie-artefact: van rechts inschuivend paneel (smal) of een eigen
 *  kolom naast de chat (breed). De inhoud zelf staat in `ArtefactInhoud` en wordt gedeeld met de
 *  losse pagina `/annotaties/<slug>`.
 *
 *  `onEscape` is bewust een no-op: de inhoud handelt Escape zelf af, want alleen die kent de lagen
 *  (selectie → bedieningsrij → gekozen element → sluiten). Zou `Dialog` hem óók afvangen, dan
 *  sprong Escape meteen door alle lagen heen. */
export function ArtefactPaneel({ variant = "side", onSluit, ...inhoud }: Props) {
  const opschrift = `${inhoud.info.citeertitel || inhoud.doc.bwbId} — artikel ${inhoud.info.artikel}${
    inhoud.doc.lid ? ` lid ${inhoud.doc.lid}` : ""
  }`;
  return (
    <Dialog
      label={`Annotatie: ${opschrift}`}
      variant={variant}
      onSluit={onSluit}
      onEscape={() => {}}
    >
      <ArtefactInhoud {...inhoud} onSluiten={onSluit} />
    </Dialog>
  );
}
