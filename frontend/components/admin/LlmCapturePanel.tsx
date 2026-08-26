"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, Section } from "@/components/ui/Card";
import { Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import { getLlmCalls, getSettings, isApiError, setCaptureLlmCalls } from "@/lib/api";
import type { LlmCall } from "@/lib/types";

function foutTekst(e: unknown): string {
  return isApiError(e) ? e.detail : (e as Error).message;
}

export function LlmCapturePanel() {
  const [capture, setCapture] = useState<boolean | null>(null);
  const [bezig, setBezig] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  const [projectId, setProjectId] = useState("");
  const [calls, setCalls] = useState<LlmCall[] | null>(null);
  const [callsFout, setCallsFout] = useState<string | null>(null);
  const [laadt, setLaadt] = useState(false);

  useEffect(() => {
    let levend = true;
    getSettings()
      .then((s) => levend && setCapture(s.capture_llm_calls))
      .catch((e) => levend && setFout(foutTekst(e)));
    return () => {
      levend = false;
    };
  }, []);

  async function toggle() {
    if (capture === null) return;
    setBezig(true);
    setFout(null);
    try {
      const s = await setCaptureLlmCalls(!capture);
      setCapture(s.capture_llm_calls);
    } catch (e) {
      setFout(foutTekst(e));
    } finally {
      setBezig(false);
    }
  }

  async function ophalen() {
    const id = projectId.trim();
    if (!id) return;
    setLaadt(true);
    setCallsFout(null);
    setCalls(null);
    try {
      setCalls(await getLlmCalls(id));
    } catch (e) {
      setCallsFout(foutTekst(e));
    } finally {
      setLaadt(false);
    }
  }

  return (
    <Section title="LLM-invoer vastleggen" subtitle="prompts + respons, voor analyse">
      <Card className="mb-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-[16rem] flex-1">
            <p className="text-sm font-medium text-ink">Vastleggen van LLM-calls</p>
            <p className="mt-0.5 text-xs text-muted">
              Legt per call de letterlijke system/user-prompt en de ruwe respons vast (incl.
              auto-correctie en gefaalde calls). Standaard uit; aanzetten kost extra opslag per analyse.
            </p>
          </div>
          <div className="flex items-center gap-3">
            {capture !== null && <Tag>{capture ? "aan" : "uit"}</Tag>}
            <Button
              variant={capture ? "secondary" : "primary"}
              onClick={() => void toggle()}
              disabled={capture === null || bezig}
            >
              {bezig ? "Bezig…" : capture ? "Uitzetten" : "Aanzetten"}
            </Button>
          </div>
        </div>
        {fout && (
          <Melding type="fout" compact className="mt-3">
            {fout}
          </Melding>
        )}
      </Card>

      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end">
        <div className="sm:min-w-[16rem] sm:flex-1">
          <span className="mb-1 block text-sm font-medium text-ink">Analyse-id</span>
          <Input
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="bv. successiewet-art-9"
            onKeyDown={(e) => e.key === "Enter" && void ophalen()}
          />
        </div>
        <Button
          variant="secondary"
          onClick={() => void ophalen()}
          disabled={laadt || !projectId.trim()}
          className="w-full sm:w-auto"
        >
          {laadt ? "Ophalen…" : "Calls ophalen"}
        </Button>
      </div>

      {callsFout && (
        <Melding type="fout" compact>
          {callsFout}
        </Melding>
      )}

      {calls && calls.length === 0 && (
        <Melding type="uitleg" compact>
          Geen vastgelegde calls voor deze analyse (stond capture aan tijdens het draaien?).
        </Melding>
      )}

      {calls && calls.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-faint">{calls.length} call(s)</p>
          {calls.map((c) => (
            <details key={c.id} className="rounded-button border border-line bg-surface">
              <summary className="flex cursor-pointer flex-wrap items-center gap-2 px-4 py-2 text-sm">
                <span className="font-mono text-xs text-faint">#{c.id}</span>
                <Tag>{c.activiteit || "—"}</Tag>
                <span className="text-xs text-muted">
                  ronde {c.ronde} · poging {c.poging}
                </span>
                {c.fase && <span className="text-xs text-muted">· {c.fase}</span>}
                {!c.ok && <span className="text-xs font-medium text-fout">fout</span>}
                <span className="ml-auto font-mono text-xs text-faint">
                  {c.tokens_in}→{c.tokens_out} tok
                </span>
              </summary>
              <div className="space-y-3 border-t border-line px-4 py-3 text-sm">
                <div className="text-xs text-muted">
                  {c.provider} · {c.model} · {c.tijdstip}
                </div>
                {c.error && (
                  <Melding type="fout" compact>
                    {c.error}
                  </Melding>
                )}
                <Veld label="System-prompt" tekst={c.system_prompt} />
                <Veld label="User-prompt" tekst={c.user_prompt} />
                <Veld label="Ruwe respons" tekst={c.response_text} />
              </div>
            </details>
          ))}
        </div>
      )}
    </Section>
  );
}

function Veld({ label, tekst }: { label: string; tekst: string }) {
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-faint">{label}</p>
      <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-field border border-line bg-paper p-3 font-mono text-xs text-ink">
        {tekst || "—"}
      </pre>
    </div>
  );
}
