"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card, Section } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import { createApiToken, isApiError, listApiTokens, revokeApiToken } from "@/lib/api";
import type { ApiTokenOut } from "@/lib/types";

export function ApiTokensPanel() {
  const [tokens, setTokens] = useState<ApiTokenOut[] | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  // Eenmalig getoond volledig token (na genereren) — daarna niet meer op te vragen.
  const [nieuw, setNieuw] = useState<{ label: string; token: string } | null>(null);

  const laad = useCallback(async () => {
    setFout(null);
    try {
      setTokens(await listApiTokens());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setTokens([]);
    }
  }, []);

  useEffect(() => {
    laad();
  }, [laad]);

  function melden(e: unknown) {
    setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
  }

  async function onGenereer(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    try {
      const res = await createApiToken(label.trim());
      setNieuw({ label: res.label, token: res.token });
      setLabel("");
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  async function onIntrek(t: ApiTokenOut) {
    if (!confirm(`Token "${t.label || t.token_prefix}" intrekken? Toepassingen die het gebruiken verliezen toegang.`)) return;
    try {
      await revokeApiToken(t.id);
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  function datum(iso: string | null): string {
    if (!iso) return "nooit";
    return new Date(iso).toLocaleString("nl-NL");
  }

  return (
    <Section
      title="API-tokens"
      count={tokens?.length}
      subtitle="Programmatische admin-toegang (bv. de admin-MCP)"
    >
      {fout && (
        <Melding type="fout" className="mb-3">
          {fout}
        </Melding>
      )}

      {nieuw && (
        <Melding type="waarschuwing" titel="Token — kopieer dit nu" className="mb-3">
          <p className="text-sm">
            Voor <span className="font-medium">{nieuw.label || "(geen label)"}</span>:
          </p>
          <code className="mt-1 block break-all rounded bg-paper px-1.5 py-1 font-mono text-xs">
            {nieuw.token}
          </code>
          <p className="mt-1 text-xs text-muted">
            Dit volledige token wordt <span className="font-medium">niet opnieuw getoond</span>. Bewaar het veilig
            (bijv. als lokale env-var voor de MCP); intrekken kan hieronder.
          </p>
          <ButtonRow align="start" className="mt-2">
            <Button size="sm" variant="secondary" onClick={() => navigator.clipboard?.writeText(nieuw.token).catch(() => {})}>
              Kopiëren
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setNieuw(null)}>
              Sluiten
            </Button>
          </ButtonRow>
        </Melding>
      )}

      <form onSubmit={onGenereer} className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="min-w-[14rem] flex-1">
          <Field label="Label">
            <Input
              type="text"
              required
              placeholder="claude-admin-mcp"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </Field>
        </div>
        <Button type="submit" className="w-full sm:w-auto">
          Token genereren
        </Button>
      </form>

      {tokens === null ? (
        <p className="text-sm text-muted">Laden…</p>
      ) : tokens.length === 0 ? (
        <p className="text-sm text-muted">Nog geen API-tokens.</p>
      ) : (
        <div className="space-y-3">
          {tokens.map((t) => (
            <Card key={t.id} className="p-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-display font-semibold text-ink">{t.label || "(geen label)"}</span>
                <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-xs text-muted">{t.token_prefix}…</code>
                <Tag>{t.scope}</Tag>
                {!t.active && (
                  <span className="inline-flex items-center rounded-full border border-fout/40 bg-fout/10 px-2.5 py-0.5 text-xs font-medium text-fout">
                    ingetrokken
                  </span>
                )}
                <span className="ml-auto text-xs text-faint">laatst gebruikt: {datum(t.last_used)}</span>
              </div>
              {t.active && (
                <ButtonRow align="start" className="mt-3">
                  <Button size="sm" variant="danger" onClick={() => onIntrek(t)}>
                    Intrekken
                  </Button>
                </ButtonRow>
              )}
            </Card>
          ))}
        </div>
      )}
    </Section>
  );
}
