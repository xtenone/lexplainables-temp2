import { ProjectForm } from "@/components/ProjectForm";

export const metadata = { title: "Nieuwe analyse · Wetsanalyse" };

export default function NieuwPagina() {
  return (
    <div className="animate-rise mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl font-semibold text-lint">Nieuwe analyse</h1>
        <p className="mt-1 text-sm text-muted">
          De orchestrator haalt de wettekst op via de wettenbank en doorloopt activiteit 2 en 3. Met
          review aan pauzeert hij na elke activiteit voor jouw akkoord.
        </p>
      </div>
      <ProjectForm />
    </div>
  );
}
