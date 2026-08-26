import { AnnotatiesClient } from "@/components/annotaties/AnnotatiesClient";
import { weergaveUitParam } from "@/lib/annotatieOverzicht";

export const metadata = { title: "Annotaties · Wetsanalyse" };

/** Het annotatie-overzicht. De pagina draagt zelf haar volle hoogte (er is geen globale chrome) en
 *  leest alleen de beginweergave uit de URL; de rest doet de client. */
export default async function AnnotatiesPagina({
  searchParams,
}: {
  searchParams: Promise<{ weergave?: string }>;
}) {
  const { weergave } = await searchParams;
  return <AnnotatiesClient beginWeergave={weergaveUitParam(weergave)} />;
}
