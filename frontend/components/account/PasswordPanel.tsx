"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, Section } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { changePassword, isApiError } from "@/lib/api";

export function PasswordPanel() {
  const [huidig, setHuidig] = useState("");
  const [nieuw, setNieuw] = useState("");
  const [herhaling, setHerhaling] = useState("");
  const [fout, setFout] = useState<string | null>(null);
  const [klaar, setKlaar] = useState(false);
  const [bezig, setBezig] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    setKlaar(false);
    if (nieuw.length < 8) {
      setFout("Kies een nieuw wachtwoord van minimaal 8 tekens.");
      return;
    }
    if (nieuw !== herhaling) {
      setFout("De nieuwe wachtwoorden komen niet overeen.");
      return;
    }
    setBezig(true);
    try {
      await changePassword(huidig, nieuw);
      setHuidig("");
      setNieuw("");
      setHerhaling("");
      setKlaar(true);
    } catch (e) {
      setFout(isApiError(e) ? e.detail : (e as Error).message);
    } finally {
      setBezig(false);
    }
  }

  return (
    <Section title="Wachtwoord wijzigen" subtitle="Self-service">
      <Card className="p-4">
        {fout && (
          <Melding type="fout" className="mb-3">
            {fout}
          </Melding>
        )}
        {klaar && (
          <Melding type="bevestiging" className="mb-3">
            Je wachtwoord is gewijzigd.
          </Melding>
        )}
        <form onSubmit={onSubmit} className="max-w-sm space-y-4">
          <Field label="Huidig wachtwoord" required>
            <Input
              type="password"
              autoComplete="current-password"
              required
              value={huidig}
              onChange={(e) => setHuidig(e.target.value)}
            />
          </Field>
          <Field label="Nieuw wachtwoord" hint="minimaal 8 tekens" required>
            <Input
              type="password"
              autoComplete="new-password"
              required
              value={nieuw}
              onChange={(e) => setNieuw(e.target.value)}
            />
          </Field>
          <Field label="Nieuw wachtwoord herhalen" required>
            <Input
              type="password"
              autoComplete="new-password"
              required
              value={herhaling}
              onChange={(e) => setHerhaling(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={bezig} className="w-full sm:w-auto">
            {bezig ? "Bezig…" : "Wachtwoord wijzigen"}
          </Button>
        </form>
      </Card>
    </Section>
  );
}
