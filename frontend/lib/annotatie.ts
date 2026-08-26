import type { DocumentStatus } from "./types";

// Presentatie-helpers voor de annotatie-workbench (vgl. lib/states.ts voor de analyse-jobs).

export const DOCUMENT_STATUS_LABEL: Record<DocumentStatus, string> = {
  in_review: "In behandeling",
  geaccordeerd: "Geaccordeerd",
  gepromoveerd: "In de graaf",
};

// Badge-tone per status (Tailwind, Rijkshuisstijl): in behandeling = aandacht-oranje,
// geaccordeerd = succes-groen, in de graaf = lintblauw.
export const DOCUMENT_STATUS_STYLE: Record<DocumentStatus, string> = {
  in_review: "bg-[#fbefe2] text-[#8e4600] border-[#e7c9a8]",
  geaccordeerd: "bg-[#e6f0e0] text-[#2c6608] border-[#bcd9a8]",
  gepromoveerd: "bg-[#e7eef5] text-[#154273] border-[#bcd2e6]",
};

export function documentStatusLabel(status: DocumentStatus): string {
  return DOCUMENT_STATUS_LABEL[status] ?? status;
}
