import { WorkbenchShell } from "@/components/werkplek/WorkbenchShell";

export const metadata = { title: "Lex · Wetsanalyse" };

/** De werkplek beheert zijn eigen hoogte en scroll: vol-bleed, precies één viewport hoog. Die
 *  container stond eerder in de globale layout; nu die kaal is, draagt de pagina hem zelf. Zonder
 *  deze klasse scrolt de chat als document en staat de invoerbalk niet meer gepind onderaan. */
export default async function WerkplekPagina({
  searchParams,
}: {
  searchParams: Promise<{ gesprek?: string; annotatie?: string }>;
}) {
  // Deep-links vanuit het annotatie-overzicht: open dit gesprek, en/of dit artefact.
  const { gesprek, annotatie } = await searchParams;
  return (
    <div className="h-screen h-[100dvh] overflow-hidden">
      <WorkbenchShell beginGesprekId={gesprek ?? null} beginArtefact={annotatie} />
    </div>
  );
}
