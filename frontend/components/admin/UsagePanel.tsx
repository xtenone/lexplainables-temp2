"use client";

import { useEffect, useState } from "react";
import { Card, Section } from "@/components/ui/Card";
import { Melding } from "@/components/ui/Melding";
import { getUsage, isApiError } from "@/lib/api";
import type { UsageReport } from "@/lib/types";

const GROUPS: { key: string; label: string }[] = [
  { key: "model", label: "Model" },
  { key: "model_profile", label: "Profiel" },
  { key: "client_id", label: "Client" },
];

function fmt(n: number): string {
  return n.toLocaleString("nl-NL");
}

export function UsagePanel() {
  const [groupBy, setGroupBy] = useState("model");
  const [rapport, setRapport] = useState<UsageReport | null>(null);
  const [fout, setFout] = useState<string | null>(null);

  useEffect(() => {
    let levend = true;
    setFout(null);
    getUsage(groupBy)
      .then((r) => levend && setRapport(r))
      .catch((e) => levend && setFout(isApiError(e) ? e.detail : (e as Error).message));
    return () => {
      levend = false;
    };
  }, [groupBy]);

  return (
    <Section title="Token-verbruik" subtitle="over alle analyses">
      <div className="mb-3 flex flex-wrap gap-2">
        {GROUPS.map((g) => (
          <button
            key={g.key}
            onClick={() => setGroupBy(g.key)}
            className={`inline-flex min-h-[36px] items-center justify-center rounded-md border px-3 py-1.5 text-xs font-medium transition-colors ${
              groupBy === g.key
                ? "border-accent/40 bg-accent/10 text-accent"
                : "border-line bg-surface text-muted hover:bg-paper"
            }`}
          >
            {g.label}
          </button>
        ))}
      </div>

      {fout && <Melding type="fout">{fout}</Melding>}

      {rapport && (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead>
              <tr className="border-b border-line bg-paper/50 text-left text-xs text-faint">
                <th className="px-4 py-2 font-medium">{GROUPS.find((g) => g.key === groupBy)?.label}</th>
                <th className="px-4 py-2 text-right font-medium">Tokens in</th>
                <th className="px-4 py-2 text-right font-medium">Tokens uit</th>
                <th className="px-4 py-2 text-right font-medium">Rondes</th>
                <th className="px-4 py-2 text-right font-medium">Analyses</th>
              </tr>
            </thead>
            <tbody>
              {rapport.rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-muted">Nog geen verbruik geregistreerd.</td>
                </tr>
              )}
              {rapport.rows.map((r) => (
                <tr key={r.sleutel} className="border-b border-line/60">
                  <td className="px-4 py-2 font-mono text-xs text-ink">{r.sleutel || "—"}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt(r.tokens_in)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt(r.tokens_out)}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-muted">{r.rondes}</td>
                  <td className="px-4 py-2 text-right tabular-nums text-muted">{r.analyses}</td>
                </tr>
              ))}
            </tbody>
            {rapport.rows.length > 0 && (
              <tfoot>
                <tr className="bg-paper/50 font-medium text-ink">
                  <td className="px-4 py-2">Totaal</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt(rapport.totaal.tokens_in)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{fmt(rapport.totaal.tokens_out)}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{rapport.totaal.rondes}</td>
                  <td className="px-4 py-2 text-right tabular-nums">{rapport.totaal.analyses}</td>
                </tr>
              </tfoot>
            )}
          </table>
          </div>
        </Card>
      )}
    </Section>
  );
}
