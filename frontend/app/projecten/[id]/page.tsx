import Link from "next/link";
import { getProjectServer } from "@/lib/server";
import { ProjectClient } from "./ProjectClient";
import { Card } from "@/components/ui/Card";
import type { Job } from "@/lib/types";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ id: string }> };

export default async function ProjectDetailPagina({ params }: Props) {
  const { id } = await params;

  let job: Job | null = null;
  let foutStatus: number | null = null;
  try {
    job = await getProjectServer(id);
  } catch (e) {
    foutStatus = (e as Error & { status?: number }).status ?? 500;
  }

  if (!job) {
    return (
      <Card className="animate-rise p-8 text-center">
        <p className="font-display text-lg text-ink">
          {foutStatus === 404 ? "Project niet gevonden" : "Project niet geladen"}
        </p>
        <p className="mt-1 text-sm text-muted">
          {foutStatus === 404
            ? "Dit project bestaat niet (meer) of hoort bij een andere client."
            : `De API gaf een fout (${foutStatus}).`}
        </p>
        <Link href="/" className="mt-4 inline-block text-sm text-link hover:underline">
          ← Terug naar projecten
        </Link>
      </Card>
    );
  }

  return <ProjectClient initieel={job} />;
}
