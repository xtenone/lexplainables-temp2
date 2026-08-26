"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card, Section } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import {
  deleteProfile,
  deleteWet,
  isApiError,
  listProfiles,
  listWetCatalog,
  setDefaultProfile,
  testProfile,
} from "@/lib/api";
import type { LlmProfileOut, TestResult, WetOut } from "@/lib/types";
import { ProfileEditor } from "./ProfileEditor";
import { WetEditor } from "./WetEditor";
import { UsagePanel } from "./UsagePanel";
import { UsersPanel } from "./UsersPanel";
import { ApiTokensPanel } from "./ApiTokensPanel";
import { LlmCapturePanel } from "./LlmCapturePanel";

type EditState =
  | { open: false }
  | { open: true; kind: "profile"; profile: LlmProfileOut | null }
  | { open: true; kind: "wet"; wet: WetOut | null };

export function BeheerClient() {
  const [profielen, setProfielen] = useState<LlmProfileOut[] | null>(null);
  const [wetten, setWetten] = useState<WetOut[] | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditState>({ open: false });
  const [tests, setTests] = useState<Record<string, TestResult | "bezig">>({});

  const laad = useCallback(async () => {
    setFout(null);
    try {
      setProfielen(await listProfiles());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setProfielen([]);
    }
    try {
      setWetten(await listWetCatalog());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setWetten([]);
    }
  }, []);

  useEffect(() => {
    laad();
  }, [laad]);

  async function onTest(name: string) {
    setTests((t) => ({ ...t, [name]: "bezig" }));
    try {
      const res = await testProfile(name);
      setTests((t) => ({ ...t, [name]: res }));
    } catch (e) {
      setTests((t) => ({
        ...t,
        [name]: { ok: false, model: "", tokens_in: 0, tokens_out: 0, detail: isApiError(e) ? e.detail : (e as Error).message },
      }));
    }
  }

  async function onDefault(name: string) {
    try {
      await setDefaultProfile(name);
      await laad();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  async function onDelete(name: string) {
    if (!confirm(`Profiel "${name}" verwijderen?`)) return;
    try {
      await deleteProfile(name);
      await laad();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  async function onDeleteWet(bwbId: string) {
    if (!confirm(`Wet "${bwbId}" verwijderen?`)) return;
    try {
      await deleteWet(bwbId);
      await laad();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  if (edit.open && edit.kind === "profile") {
    return (
      <ProfileEditor
        profile={edit.profile}
        onCancel={() => setEdit({ open: false })}
        onDone={() => {
          setEdit({ open: false });
          laad();
        }}
      />
    );
  }

  if (edit.open && edit.kind === "wet") {
    return (
      <WetEditor
        wet={edit.wet}
        onCancel={() => setEdit({ open: false })}
        onDone={() => {
          setEdit({ open: false });
          laad();
        }}
      />
    );
  }

  return (
    <div className="space-y-8">
      <Section title="Modelprofielen" count={profielen?.length} subtitle="LLM-configuratie">
        {fout && <Melding type="fout" className="mb-3">{fout}</Melding>}
        <ButtonRow className="mb-4">
          <Button onClick={() => setEdit({ open: true, kind: "profile", profile: null })}>Nieuw profiel</Button>
        </ButtonRow>

        {profielen === null ? (
          <p className="text-sm text-muted">Laden…</p>
        ) : profielen.length === 0 ? (
          <p className="text-sm text-muted">Nog geen profielen.</p>
        ) : (
          <div className="space-y-3">
            {profielen.map((p) => {
              const test = tests[p.name];
              return (
                <Card key={p.name} className="p-4">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-display font-semibold text-ink">{p.name}</span>
                    {p.is_default && (
                      <span className="inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
                        default
                      </span>
                    )}
                    <Tag>{p.provider}</Tag>
                    <Tag>{p.model || "geen model"}</Tag>
                    {p.api_key_set && <Tag>key ✓</Tag>}
                    <span className="ml-auto text-xs text-faint">
                      {p.verbruik
                        ? `${(p.verbruik.tokens_in + p.verbruik.tokens_out).toLocaleString("nl-NL")} tokens · ${p.verbruik.analyses} analyses`
                        : "geen verbruik"}
                    </span>
                  </div>

                  {test && test !== "bezig" && (
                    <Melding
                      type={test.ok ? "bevestiging" : "fout"}
                      compact
                      className="mt-3 text-xs"
                    >
                      {test.ok
                        ? `Verbinding OK — model ${test.model} (${test.tokens_in + test.tokens_out} tokens).`
                        : `Test mislukt: ${test.detail}`}
                    </Melding>
                  )}

                  <ButtonRow align="start" className="mt-3">
                    <Button size="sm" variant="secondary" onClick={() => setEdit({ open: true, kind: "profile", profile: p })}>
                      Bewerken
                    </Button>
                    <Button size="sm" variant="secondary" onClick={() => onTest(p.name)} disabled={test === "bezig"}>
                      {test === "bezig" ? "Testen…" : "Test verbinding"}
                    </Button>
                    {!p.is_default && (
                      <Button size="sm" variant="ghost" onClick={() => onDefault(p.name)}>
                        Als default
                      </Button>
                    )}
                    {!p.is_default && (
                      <Button size="sm" variant="danger" onClick={() => onDelete(p.name)}>
                        Verwijderen
                      </Button>
                    )}
                  </ButtonRow>
                </Card>
              );
            })}
          </div>
        )}
      </Section>

      <Section title="Wetten" count={wetten?.length} subtitle="Selecteerbaar bij nieuwe analyse">
        <ButtonRow className="mb-4">
          <Button onClick={() => setEdit({ open: true, kind: "wet", wet: null })}>Nieuwe wet</Button>
        </ButtonRow>

        {wetten === null ? (
          <p className="text-sm text-muted">Laden…</p>
        ) : wetten.length === 0 ? (
          <p className="text-sm text-muted">Nog geen wetten. Voeg er een toe om de dropdown te vullen.</p>
        ) : (
          <div className="space-y-3">
            {wetten.map((w) => (
              <Card key={w.bwbId} className="p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <span className="font-display font-semibold text-ink">{w.naam || "(geen naam)"}</span>
                  <Tag>{w.bwbId}</Tag>
                </div>
                <ButtonRow align="start" className="mt-3">
                  <Button size="sm" variant="secondary" onClick={() => setEdit({ open: true, kind: "wet", wet: w })}>
                    Bewerken
                  </Button>
                  <Button size="sm" variant="danger" onClick={() => onDeleteWet(w.bwbId)}>
                    Verwijderen
                  </Button>
                </ButtonRow>
              </Card>
            ))}
          </div>
        )}
      </Section>

      <UsersPanel />

      <ApiTokensPanel />

      <UsagePanel />

      <LlmCapturePanel />
    </div>
  );
}
