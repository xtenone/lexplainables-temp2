import { getProjectsServer } from "@/lib/server";
import { LinkButton } from "@/components/ui/Button";
import { Melding } from "@/components/ui/Melding";
import { Vormelement } from "@/components/ui/Vormelement";
import { ProjectenLijstClient } from "./ProjectenLijstClient";
import type { JobSummary } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function ProjectenPagina() {
  let projecten: JobSummary[] = [];
  let fout: string | null = null;
  try {
    projecten = await getProjectsServer();
  } catch (e) {
    fout = (e as Error).message;
  }

  return (
    <div className="animate-rise space-y-8">
      <Vormelement className="px-6 py-8 sm:px-10 sm:py-10">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-prose">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-paper/70">
              Juridisch Analyseschema
            </p>
            <h1 className="mt-2 font-display text-3xl font-semibold text-paper">Analyses</h1>
            <p className="mt-2 text-sm text-paper/85">
              Elke analyse duidt een werkgebied — één of meer bronnen (wetsartikel of lid) —
              brongetrouw volgens het Juridisch Analyseschema: markeren &amp; classificeren,
              daarna begrippen &amp; afleidingsregels.
            </p>
          </div>
          <LinkButton href="/nieuw" variant="secondary" className="w-full sm:w-auto sm:self-start">
            Nieuwe analyse
          </LinkButton>
        </div>
      </Vormelement>

      {fout ? (
        <Melding type="fout">
          De API is niet bereikbaar: <span className="font-mono">{fout}</span>. Controleer{" "}
          <span className="font-mono">API_BASE_URL</span> en het token.
        </Melding>
      ) : (
        <ProjectenLijstClient initieel={projecten} />
      )}
    </div>
  );
}
