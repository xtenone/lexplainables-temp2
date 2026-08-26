import { AnnotatieDetailClient } from "@/components/annotaties/AnnotatieDetailClient";

export const metadata = { title: "Annotatie · Wetsanalyse" };

/** Eén annotatie als eigen pagina — het artefact los van het gesprek, met een deelbare URL. */
export default async function AnnotatiePagina({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  return <AnnotatieDetailClient slug={slug} />;
}
