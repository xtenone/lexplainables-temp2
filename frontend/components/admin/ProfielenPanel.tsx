"use client";

import { Vinkje } from "@/components/ui/Icoon";
import { BevestigKnop } from "@/components/ui/BevestigKnop";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card } from "@/components/ui/Card";
import { SettingGroup } from "@/components/ui/SettingRow";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import { deleteProfile, isApiError, listProfiles, setDefaultProfile, testProfile } from "@/lib/api";
import type { LlmProfileOut, TestResult } from "@/lib/types";
import { ProfileEditor } from "./ProfileEditor";

type EditState = { open: false } | { open: true; profile: LlmProfileOut | null };

export function ProfielenPanel() {
  const [profielen, setProfielen] = useState<LlmProfileOut[] | null>(null);
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
    try {
      await deleteProfile(name);
      await laad();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    }
  }

  if (edit.open) {
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

  return (
    <div>
      <SettingGroup titel="Modelprofielen" count={profielen?.length} omschrijving="LLM-configuratie. De API-key wordt versleuteld bewaard en nooit getoond.">
        {fout && <Melding type="fout" className="mb-3">{fout}</Melding>}
        <ButtonRow className="mb-4">
          <Button size="sm" onClick={() => setEdit({ open: true, profile: null })}>Nieuw profiel</Button>
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
                <Card key={p.name} className="p-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <span className="font-display font-semibold text-ink">{p.name}</span>
                    {p.is_default && (
                      <span className="inline-flex items-center rounded-full border border-accent/40 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent">
                        default
                      </span>
                    )}
                    <Tag>{p.provider}</Tag>
                    <Tag>{p.model || "geen model"}</Tag>
                    {p.api_key_set && <Tag><span className="inline-flex items-center gap-1">key <Vinkje /></span></Tag>}
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
                    <Button size="sm" variant="secondary" onClick={() => setEdit({ open: true, profile: p })}>
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
                      <BevestigKnop
                        onBevestig={() => onDelete(p.name)}
                        bevestigTekst={`"${p.name}" verwijderen?`}
                        className="focus-ring inline-flex min-h-[40px] shrink-0 items-center justify-center rounded-field border border-fout px-3 text-sm font-medium text-fout transition coarse:min-h-[48px]"
                        bevestigClassName="bg-fout text-paper"
                      >
                        Verwijderen
                      </BevestigKnop>
                    )}
                  </ButtonRow>
                </Card>
              );
            })}
          </div>
        )}
      </SettingGroup>
    </div>
  );
}
