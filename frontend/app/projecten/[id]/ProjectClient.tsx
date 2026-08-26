"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { StateBadge, Tag } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card } from "@/components/ui/Card";
import { Tabs } from "@/components/ui/Tabs";
import { DownloadMenu, type DownloadItem } from "@/components/ui/DownloadMenu";
import { Melding } from "@/components/ui/Melding";
import { StatusTimeline } from "@/components/StatusTimeline";
import { ReviewPanel } from "@/components/ReviewPanel";
import { RapportView } from "@/components/RapportView";
import { RegelspraakView } from "@/components/RegelspraakView";
import {
  getProject, getRapport, getRegelspraak, startAct3, startRegelspraak, retryProject, deleteProject, isApiError,
} from "@/lib/api";
import { isTerminal, reviewActiviteit } from "@/lib/states";
import { pathSegment } from "@/lib/url";
import type { Job, Rapport, RegelspraakModel } from "@/lib/types";
import { useRouter } from "next/navigation";

/** Korte uitleg in mensentaal bij een foutklasse, zodat de pagina niet alleen een kale code toont. */
function foutUitleg(klasse: string): string {
  switch (klasse) {
    case "validatie":
      return "De analyse voldeed niet aan de brongetrouwheid-eisen — bijvoorbeeld een markering waarvan de formulering niet letterlijk in de wettekst staat. Dit corrigeer je via de review.";
    case "mcp":
      return "De wettekst kon niet uit de wettenbank worden opgehaald. Vaak tijdelijk; later opnieuw proberen helpt meestal.";
    case "llm":
      return "Het taalmodel gaf een fout of ongeldig antwoord. Opnieuw proberen lost dit doorgaans op.";
    case "quota":
      return "Het tokenbudget voor deze analyse is bereikt.";
    case "intern":
      return "De analyse werd onderbroken, bijvoorbeeld door een herstart van de dienst.";
    default:
      return "Er ging iets mis tijdens de analyse.";
  }
}

export function ProjectClient({ initieel }: { initieel: Job }) {
  const router = useRouter();
  const [job, setJob] = useState<Job>(initieel);
  const [rapport, setRapport] = useState<Rapport | null>(null);
  const [rapportFout, setRapportFout] = useState<string | null>(null);
  const [rapportBezig, setRapportBezig] = useState(false);
  const [regelspraak, setRegelspraak] = useState<RegelspraakModel | null>(null);
  const [regelspraakFout, setRegelspraakFout] = useState<string | null>(null);
  const [regelspraakBezig, setRegelspraakBezig] = useState(false);
  const [startFout, setStartFout] = useState<string | null>(null);
  const [actieFout, setActieFout] = useState<string | null>(null);
  const [actie, setActie] = useState<string | null>(null);
  const [tab, setTab] = useState<"analyse" | "regelspraak">("analyse");
  // Wordt opgehoogd bij het starten van de regelspraak-fase, zodat de SSE-stream heropent vanuit
  // een (terminale) `klaar`-state.
  const [streamGen, setStreamGen] = useState(0);
  const esRef = useRef<EventSource | null>(null);

  const isKlaarachtig = job.state === "klaar" || job.state === "rs-klaar";

  const refreshJob = useCallback(async () => {
    try {
      setJob(await getProject(initieel.id));
    } catch {
      /* tijdelijke leesfout; volgende tick probeert opnieuw */
    }
  }, [initieel.id]);

  // SSE: open zolang het project niet terminaal is; elke update triggert een verse job-fetch.
  useEffect(() => {
    // streamGen === 0 → eerste mount: een terminale analyse opent géén stream (niets te volgen).
    // streamGen > 0 → geforceerde heropening (start regelspraak vanuit het terminale `klaar`): open
    // ongeacht de — nu nog terminale — job.state, zodat de detailpagina de rs-overgang live oppikt.
    if (streamGen === 0 && isTerminal(job.state)) return;
    const es = new EventSource(`/api/projects/${pathSegment(initieel.id)}/events`);
    esRef.current = es;
    es.onmessage = () => void refreshJob();
    es.addEventListener("done", () => {
      void refreshJob();
      es.close();
    });
    // Bij een streamfout laten we de browser vanzelf herverbinden; het sluiten zodra de analyse
    // terminaal is, doet het aparte effect hieronder (dat de actuele job.state ziet). Hier géén
    // job.state-check: die zou de stale waarde uit deze closure lezen.
    return () => es.close();
    // We heropenen bewust niet bij elke state-wijziging: één stream volstaat tot terminaal.
    // streamGen forceert wél een heropening (bv. bij het starten van de regelspraak-fase vanuit klaar).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initieel.id, streamGen]);

  // Sluit de stream zodra we terminaal zijn.
  useEffect(() => {
    if (isTerminal(job.state)) esRef.current?.close();
  }, [job.state]);

  // Rapport ophalen zodra klaar. Een mislukte fetch wordt zichtbaar gemaakt (niet stil ingeslikt),
  // zodat de pagina niet eindeloos op "Rapport laden…" blijft staan bij bv. een tijdelijke storing.
  const laadRapport = useCallback(async () => {
    setRapportBezig(true);
    setRapportFout(null);
    try {
      setRapport(await getRapport(initieel.id));
    } catch (e) {
      setRapportFout(isApiError(e) ? e.detail : (e as Error).message);
    } finally {
      setRapportBezig(false);
    }
  }, [initieel.id]);

  useEffect(() => {
    // Guards op fout/bezig voorkomen een herhaal-loop: na een fout blijft het bij die ene poging
    // tot de gebruiker op "Opnieuw proberen" klikt. Het rapport blijft beschikbaar ná de
    // regelspraak-fase (rs-klaar), dus ook dan laden.
    if (isKlaarachtig && !rapport && !rapportFout && !rapportBezig) {
      void laadRapport();
    }
  }, [isKlaarachtig, rapport, rapportFout, rapportBezig, laadRapport]);

  const laadRegelspraak = useCallback(async () => {
    setRegelspraakBezig(true);
    setRegelspraakFout(null);
    try {
      setRegelspraak(await getRegelspraak(initieel.id));
    } catch (e) {
      setRegelspraakFout(isApiError(e) ? e.detail : (e as Error).message);
    } finally {
      setRegelspraakBezig(false);
    }
  }, [initieel.id]);

  useEffect(() => {
    if (job.state === "rs-klaar" && !regelspraak && !regelspraakFout && !regelspraakBezig) {
      void laadRegelspraak();
    }
  }, [job.state, regelspraak, regelspraakFout, regelspraakBezig, laadRegelspraak]);

  async function onStartRegelspraak() {
    setActie("regelspraak");
    setStartFout(null);
    try {
      const res = await startRegelspraak(initieel.id, {});
      setJob((j) => ({ ...j, state: res.state })); // optimistisch: verlaat de klaar-kaart direct
      setStreamGen((n) => n + 1); // heropen de SSE-stream vanuit de terminale klaar-state
      await refreshJob();
    } catch (e) {
      if (isApiError(e) && e.status === 429) {
        setStartFout(
          e.retryAfter
            ? `Te veel verzoeken; probeer het over ${e.retryAfter} s opnieuw.`
            : "Te veel verzoeken; probeer het zo opnieuw.",
        );
      } else if (isApiError(e) && e.status === 409) {
        setStartFout("De RegelSpraak-fase is al gestart of de analyse is niet meer afgerond; de pagina ververst.");
        await refreshJob();
      } else {
        setStartFout(isApiError(e) ? e.detail : (e as Error).message);
      }
    }
    setActie(null);
  }

  async function onStartAct3() {
    setActie("act3");
    setStartFout(null);
    try {
      const res = await startAct3(initieel.id);
      setJob((j) => ({ ...j, state: res.state, scope: "volledig" })); // optimistisch: verlaat de klaar-kaart direct
      setStreamGen((n) => n + 1); // heropen de SSE-stream vanuit de terminale klaar-state
      await refreshJob();
    } catch (e) {
      if (isApiError(e) && e.status === 429) {
        setStartFout(
          e.retryAfter
            ? `Te veel verzoeken; probeer het over ${e.retryAfter} s opnieuw.`
            : "Te veel verzoeken; probeer het zo opnieuw.",
        );
      } else if (isApiError(e) && e.status === 409) {
        setStartFout("Activiteit 3 is al gestart of de analyse is niet meer afgerond; de pagina ververst.");
        await refreshJob();
      } else {
        setStartFout(isApiError(e) ? e.detail : (e as Error).message);
      }
    }
    setActie(null);
  }

  async function onRetry() {
    setActieFout(null);
    setActie("retry");
    try {
      await retryProject(initieel.id);
      await refreshJob();
    } catch (e) {
      setActieFout(isApiError(e) ? e.detail : (e as Error).message);
    }
    setActie(null);
  }

  async function onDelete() {
    if (!confirm("Dit project verwijderen? Dit kan niet ongedaan worden gemaakt.")) return;
    setActieFout(null);
    setActie("delete");
    try {
      await deleteProject(initieel.id);
      router.push("/");
    } catch (e) {
      setActieFout(isApiError(e) ? e.detail : (e as Error).message);
      setActie(null);
    }
  }

  const reviewAct = reviewActiviteit(job.state);
  // Retry hervat een al-weggeschreven ronde in review; alleen zonder ronde draait hij echt opnieuw.
  const heeftRonde = job.provenance.length > 0;
  const retryLabel = heeftRonde ? "Terug naar review" : "Opnieuw proberen";

  // Eén download-menu voor het hele dossier: de gecombineerde .md (+ PDF via printen) als primaire
  // acties, de losse exports als secundaire. RegelSpraak-items alleen ná de formaliseringsfase.
  const seg = pathSegment(job.id);
  const downloadItems: DownloadItem[] =
    job.state === "rs-klaar"
      ? [
          { type: "link", label: "Volledig rapport (.md)", href: `/api/projects/${seg}/rapport-volledig`, primary: true },
          { type: "action", label: "PDF (printen / opslaan)", onClick: () => window.print() },
          { type: "divider" },
          { type: "link", label: "Wetsanalyse (.md)", href: `/api/projects/${seg}/rapport-md` },
          { type: "link", label: "RegelSpraak (.rs)", href: `/api/projects/${seg}/regelspraak-rs` },
          { type: "link", label: "RegelSpraak (.md)", href: `/api/projects/${seg}/regelspraak-md` },
        ]
      : [
          { type: "link", label: "Rapport (.md)", href: `/api/projects/${seg}/rapport-md`, primary: true },
          { type: "action", label: "PDF (printen / opslaan)", onClick: () => window.print() },
        ];

  // Panelen per fase, zodat ze zowel in de tabs (rs-klaar) als los (klaar) herbruikbaar zijn.
  const analysePaneel = rapport ? (
    <RapportView rapport={rapport} />
  ) : rapportFout ? (
    <Melding type="fout" titel="Rapport kon niet worden geladen">
      <p className="mt-1 text-sm">{rapportFout}</p>
      <p className="mt-2 text-sm text-muted">
        De analyse is klaar; alleen het ophalen van het rapport mislukte (vaak tijdelijk).
      </p>
      <div className="mt-3">
        <Button variant="secondary" onClick={() => void laadRapport()} disabled={rapportBezig}>
          {rapportBezig ? "Bezig…" : "Opnieuw proberen"}
        </Button>
      </div>
    </Melding>
  ) : (
    <Card className="p-6 text-sm text-muted">Rapport laden…</Card>
  );

  const regelspraakPaneel = regelspraak ? (
    <RegelspraakView model={regelspraak} />
  ) : regelspraakFout ? (
    <Melding type="fout" titel="RegelSpraak-model kon niet worden geladen">
      <p className="mt-1 text-sm">{regelspraakFout}</p>
      <div className="mt-3">
        <Button variant="secondary" onClick={() => void laadRegelspraak()} disabled={regelspraakBezig}>
          {regelspraakBezig ? "Bezig…" : "Opnieuw proberen"}
        </Button>
      </div>
    </Melding>
  ) : (
    <Card className="p-6 text-sm text-muted">RegelSpraak-model laden…</Card>
  );

  return (
    <div className="animate-rise space-y-6">
      {/* Kop */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link href="/" className="text-xs text-faint hover:text-link">
            ← Projecten
          </Link>
          <h1 className="mt-1 font-display text-2xl font-semibold text-lint">
            {job.id}
          </h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StateBadge state={job.state} />
            {(job.bronnen ?? []).map((b, i) => (
              <Tag key={i}>
                {b.bwbId ? `${b.bwbId} ` : ""}art. {b.artikel}
                {b.lid ? ` lid ${b.lid}` : ""}
              </Tag>
            ))}
            {job.model_profile && <Tag>{job.model_profile}</Tag>}
            {!job.review && <Tag>volautomatisch</Tag>}
            {job.scope === "act2" && <Tag>alleen activiteit 2</Tag>}
          </div>
        </div>
        <ButtonRow align="end" className="print:hidden">
          {isKlaarachtig && <DownloadMenu items={downloadItems} />}
          {job.state === "fout" && (
            <Button
              variant="primary"
              onClick={onRetry}
              disabled={actie !== null}
              title={
                heeftRonde
                  ? "Heropent de laatste ronde zodat je via reviewfeedback kunt corrigeren"
                  : "Start de analyse opnieuw vanaf het begin"
              }
            >
              {actie === "retry" ? "Bezig…" : retryLabel}
            </Button>
          )}
          {isTerminal(job.state) && (
            <Button variant="danger" onClick={onDelete} disabled={actie !== null}>
              {actie === "delete" ? "Bezig…" : "Verwijderen"}
            </Button>
          )}
        </ButtonRow>
      </div>

      {actieFout && (
        <Melding type="fout" titel="Actie mislukt">
          <p className="mt-1 text-sm">{actieFout}</p>
        </Melding>
      )}

      {/* Waarschuwingen — in review-states toont de ReviewPanel ze (algemeen + per item), dus
          hier alleen buiten review om dubbele weergave te voorkomen. */}
      {job.waarschuwingen.length > 0 && !reviewAct && (
        <Melding type="waarschuwing" titel="Waarschuwingen">
          <ul className="mt-1 list-inside list-disc space-y-1 text-sm">
            {job.waarschuwingen.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </Melding>
      )}

      {/* Fout */}
      {job.state === "fout" && job.error && (
        <Melding type="fout" titel="Analyse gestopt">
          <p className="mt-1 text-sm">{job.error.bericht}</p>
          <p className="mt-2 text-sm text-muted">{foutUitleg(job.error.klasse)}</p>
          <p className="mt-3 text-sm text-muted">
            {heeftRonde ? (
              <>
                Met <strong className="text-ink">Terug naar review</strong> open je de laatste ronde
                opnieuw; verwerk de aandachtspunten als reviewfeedback en dien een nieuwe ronde in.
              </>
            ) : (
              <>
                Met <strong className="text-ink">Opnieuw proberen</strong> start de analyse opnieuw.
              </>
            )}{" "}
            Met <strong className="text-ink">Verwijderen</strong> gooi je de analyse definitief weg.
          </p>
          <p className="mt-3 text-xs text-faint">
            Stap <span className="font-mono">{job.error.stap}</span> · klasse{" "}
            <span className="font-mono">{job.error.klasse}</span>
            {job.error.ronde != null && <> · ronde {job.error.ronde}</>}
          </p>
        </Melding>
      )}

      {/* Hoofdinhoud per fase */}
      {reviewAct ? (
        <ReviewPanel
          job={job}
          activiteit={reviewAct}
          onSubmitted={refreshJob}
          onDelete={onDelete}
          verwijderBezig={actie === "delete"}
        />
      ) : job.state === "rs-klaar" ? (
        // Twee fasen, gescheiden in tabs — houdt de pagina overzichtelijk. Beide panelen blijven
        // gemount (Tabs verbergt het inactieve), zodat printen/PDF het hele dossier toont.
        <Tabs
          active={tab}
          onChange={(k) => setTab(k as "analyse" | "regelspraak")}
          tabs={[
            { key: "analyse", label: "Wetsanalyse", content: analysePaneel },
            { key: "regelspraak", label: "RegelSpraak", content: regelspraakPaneel },
          ]}
        />
      ) : isKlaarachtig ? (
        <div className="space-y-6">
          {analysePaneel}

          {job.scope === "act2" ? (
            <Card className="p-6 print:hidden">
              <h2 className="font-display text-lg font-semibold text-lint">Activiteit 3 uitvoeren</h2>
              <p className="mt-1 max-w-prose text-sm text-muted">
                Deze analyse is afgerond na activiteit 2 (markeren &amp; classificeren). Stel alsnog
                de begrippen en afleidingsregels (activiteit 3) vast op basis van de goedgekeurde
                markeringen; daarna wordt het rapport aangevuld en komt ook RegelSpraak beschikbaar.
                {job.review && " De stap kent een review-checkpoint."}
              </p>
              <div className="mt-4">
                <Button variant="primary" onClick={onStartAct3} disabled={actie !== null}>
                  {actie === "act3" ? "Starten…" : "Activiteit 3 uitvoeren"}
                </Button>
              </div>
              {startFout && (
                <div className="mt-4">
                  <Melding type="fout" titel="Starten mislukt">
                    <p className="mt-1 text-sm">{startFout}</p>
                  </Melding>
                </div>
              )}
            </Card>
          ) : (
            <Card className="p-6 print:hidden">
              <h2 className="font-display text-lg font-semibold text-lint">Formaliseren naar RegelSpraak</h2>
              <p className="mt-1 max-w-prose text-sm text-muted">
                Zet de begrippen en afleidingsregels van deze analyse om naar een uitvoerbare
                specificatie in RegelSpraak/GegevensSpraak. De fase kent twee review-checkpoints
                (objectmodel en regels), tenzij deze analyse volautomatisch draait.
              </p>
              <div className="mt-4">
                <Button variant="primary" onClick={onStartRegelspraak} disabled={actie !== null}>
                  {actie === "regelspraak" ? "Starten…" : "Naar RegelSpraak"}
                </Button>
              </div>
              {startFout && (
                <div className="mt-4">
                  <Melding type="fout" titel="Starten mislukt">
                    <p className="mt-1 text-sm">{startFout}</p>
                  </Melding>
                </div>
              )}
            </Card>
          )}
        </div>
      ) : job.state !== "fout" ? (
        <Card className="p-6">
          <p className="mb-4 text-sm text-muted">
            De analyse loopt. Deze pagina werkt live bij via een server-stream.
          </p>
          <StatusTimeline job={job} />
        </Card>
      ) : null}

      {/* Provenance (audit) */}
      {job.provenance.length > 0 && (
        <details className="group">
          <summary className="cursor-pointer text-sm text-faint hover:text-ink">
            Herkomst &amp; audit ({job.provenance.length} ronden)
          </summary>
          <Card className="mt-3 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-line text-left text-faint">
                  <th className="px-3 py-2 font-medium">Act.</th>
                  <th className="px-3 py-2 font-medium">Ronde</th>
                  <th className="px-3 py-2 font-medium">Model</th>
                  <th className="px-3 py-2 font-medium">Provider</th>
                  <th className="px-3 py-2 font-medium">Tokens</th>
                  <th className="px-3 py-2 font-medium">MCP-versie</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {job.provenance.map((p, i) => (
                  <tr key={i} className="border-b border-line/50 last:border-0">
                    <td className="px-3 py-2">{p.activiteit}</td>
                    <td className="px-3 py-2">{p.ronde}</td>
                    <td className="px-3 py-2">{p.model || "—"}</td>
                    <td className="px-3 py-2">{p.provider || "—"}</td>
                    <td className="px-3 py-2">{p.tokens_in}/{p.tokens_out}</td>
                    <td className="px-3 py-2">{p.mcp_versiedatum || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        </details>
      )}
    </div>
  );
}
