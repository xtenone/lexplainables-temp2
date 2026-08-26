"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { isApiError, resolveWetNaam, saveWet } from "@/lib/api";
import type { WetOut } from "@/lib/types";

interface Props {
  /** Bestaande wet bij bewerken; null bij nieuw. */
  wet: WetOut | null;
  onDone: () => void;
  onCancel: () => void;
}

export function WetEditor({ wet, onDone, onCancel }: Props) {
  const nieuw = wet === null;
  const [bwbId, setBwbId] = useState(wet?.bwbId ?? "");
  const [naam, setNaam] = useState(wet?.naam ?? "");
  const [bezig, setBezig] = useState(false);
  const [ophalen, setOphalen] = useState(false);
  const [fout, setFout] = useState<string | null>(null);

  async function onResolve() {
    setFout(null);
    if (!bwbId.trim()) return setFout("Vul eerst een BWB-id in.");
    setOphalen(true);
    try {
      const res = await resolveWetNaam(bwbId.trim());
      setNaam(res.naam);
    } catch (e) {
      setFout(isApiError(e) ? `Naam ophalen mislukt: ${e.detail}` : (e as Error).message);
    }
    setOphalen(false);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    if (!bwbId.trim()) return setFout("BWB-id is verplicht.");
    if (!naam.trim()) return setFout("Naam is verplicht.");

    setBezig(true);
    try {
      await saveWet(bwbId.trim(), { naam: naam.trim() });
      onDone();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setBezig(false);
    }
  }

  return (
    <Card className="p-6">
      <form onSubmit={onSubmit} className="space-y-5">
        <h3 className="font-display text-lg font-semibold text-lint">
          {nieuw ? "Nieuwe wet" : `Wet bewerken — ${wet?.bwbId}`}
        </h3>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Field label="BWB-id" required hint={nieuw ? "bv. BWBR0004770" : "vast"}>
            <Input
              value={bwbId}
              onChange={(e) => setBwbId(e.target.value)}
              disabled={!nieuw}
              placeholder="BWBR0004770"
              autoComplete="off"
            />
          </Field>
          <Field label="Naam" required hint="leesbaar label voor de dropdown">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input value={naam} onChange={(e) => setNaam(e.target.value)} placeholder="Successiewet 1956" autoComplete="off" />
              <Button type="button" variant="secondary" onClick={onResolve} disabled={ophalen} className="w-full sm:w-auto">
                {ophalen ? "Ophalen…" : "Naam ophalen"}
              </Button>
            </div>
          </Field>
        </div>

        {fout && <Melding type="fout">{fout}</Melding>}

        <ButtonRow className="pt-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={bezig}>
            Annuleren
          </Button>
          <Button type="submit" disabled={bezig}>
            {bezig ? "Bezig met opslaan…" : "Opslaan"}
          </Button>
        </ButtonRow>
      </form>
    </Card>
  );
}
