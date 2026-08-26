"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card } from "@/components/ui/Card";
import { SettingGroup } from "@/components/ui/SettingRow";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { BevestigKnop } from "@/components/ui/BevestigKnop";
import { Tag } from "@/components/ui/Badge";
import { createApiToken, isApiError, listApiTokens, revokeApiToken } from "@/lib/api";
import type { ApiTokenOut } from "@/lib/types";

export function ApiTokensPanel() {
  const [tokens, setTokens] = useState<ApiTokenOut[] | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [gekopieerd, setGekopieerd] = useState(false);
  const [bezig, setBezig] = useState(false);

  /** Kopiëren mét terugkoppeling. `navigator.clipboard` bestaat niet op een niet-beveiligde origin
   *  en kan geweigerd worden; dat stil laten gebeuren is bij een eenmalig token het slechtste
   *  antwoord — dan denk je dat je het hebt. */
  async function kopieer(token: string) {
    try {
      await navigator.clipboard.writeText(token);
      setGekopieerd(true);
      setFout(null);
    } catch {
      setFout("Kopiëren lukt niet in deze browser — selecteer het token hierboven en kopieer het zelf.");
    }
  }
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
    // Data-load bij mount: setState gebeurt async ná de fetch (geen synchrone render-cascade).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    laad();
  }, [laad]);

  function melden(e: unknown) {
    setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
  }

  async function onGenereer(e: React.FormEvent) {
    e.preventDefault();
    // Twee klikken maakten twee actieve tokens aan, waarvan alleen de tweede waarde in beeld kwam:
    // de eerste bleef als levend token in de lijst staan zonder dat iemand hem kent.
    if (bezig) return;
    setBezig(true);
    setFout(null);
    try {
      const res = await createApiToken(label.trim());
      setNieuw({ label: res.label, token: res.token });
      setGekopieerd(false); // een vers token is nog niet gekopieerd
      setLabel("");
      await laad();
    } catch (e) {
      melden(e);
    } finally {
      setBezig(false);
    }
  }

  // De bevestiging zit in de knop (twee klikken). Wát er gebeurt staat in de regel eronder, zodat
  // de waarschuwing niet in een systeemvenster zit dat je wegklikt zonder te lezen.
  async function onIntrek(t: ApiTokenOut) {
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
    <SettingGroup
      titel="API-tokens"
      count={tokens?.length}
      omschrijving="Programmatische admin-toegang, bijvoorbeeld voor de admin-MCP."
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
          {/* Selecteerbaar veld i.p.v. alleen een <code>: lukt kopiëren niet (geen beveiligde origin,
              toestemming geweigerd), dan moet handmatig selecteren altijd nog kunnen — dit token is
              eenmalig. */}
          <input
            readOnly
            value={nieuw.token}
            aria-label="API-token"
            onFocus={(e) => e.currentTarget.select()}
            className="mt-1 w-full rounded border border-line bg-paper px-1.5 py-1 font-mono text-xs text-ink"
          />
          <p className="mt-1 text-xs text-muted">
            Dit volledige token wordt <span className="font-medium">niet opnieuw getoond</span>. Bewaar het veilig
            (bijv. als lokale env-var voor de MCP); intrekken kan hieronder.
          </p>
          <ButtonRow align="start" className="mt-2">
            <Button size="sm" variant="secondary" onClick={() => void kopieer(nieuw.token)}>
              {gekopieerd ? "Gekopieerd" : "Kopiëren"}
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
        <Button size="sm" type="submit" disabled={bezig} className="w-full sm:w-auto">
          {bezig ? "Genereren…" : "Token genereren"}
        </Button>
      </form>

      {tokens === null ? (
        <p className="text-sm text-muted">Laden…</p>
      ) : tokens.length === 0 ? (
        <p className="text-sm text-muted">Nog geen API-tokens.</p>
      ) : (
        <div className="space-y-3">
          {tokens.map((t) => (
            <Card key={t.id} className="p-3">
              <div className="flex flex-wrap items-center gap-3">
                <span className="min-w-0 break-words font-display font-semibold text-ink">{t.label || "(geen label)"}</span>
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
                  <BevestigKnop
                    onBevestig={() => onIntrek(t)}
                    bevestigTekst="Intrekken?"
                    className="focus-ring inline-flex min-h-[40px] shrink-0 items-center justify-center rounded-field border border-fout px-3 text-sm font-medium text-fout transition coarse:min-h-[48px]"
                    bevestigClassName="bg-fout text-paper"
                  >
                    Intrekken
                  </BevestigKnop>
                  <span className="self-center text-xs text-muted">
                    Toepassingen die dit token gebruiken verliezen meteen toegang.
                  </span>
                </ButtonRow>
              )}
            </Card>
          ))}
        </div>
      )}
    </SettingGroup>
  );
}
