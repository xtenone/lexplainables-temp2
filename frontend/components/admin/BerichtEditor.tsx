"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { Tabs } from "@/components/ui/Tabs";
import { Markdown } from "@/components/werkplek/Markdown";
import { isApiError, maakBericht, updateBericht } from "@/lib/api";
import type { AdminBerichtOut, BerichtAanmakenIn, BerichtType } from "@/lib/types";

const TYPEN: { value: BerichtType; label: string }[] = [
  { value: "update",       label: "Update (nieuwe functie / verbetering)" },
  { value: "info",         label: "Informatie (neutraal)" },
  { value: "waarschuwing", label: "Waarschuwing (gedrag verandert)" },
  { value: "kritiek",      label: "Kritiek (dringende aandacht vereist)" },
];

interface Props {
  bericht: AdminBerichtOut | null;
  onCancel: () => void;
  onDone: () => void;
}

export function BerichtEditor({ bericht, onCancel, onDone }: Props) {
  const [titel, setTitel] = useState(bericht?.titel ?? "");
  const [inhoud, setInhoud] = useState(bericht?.inhoud ?? "");
  const [type, setType] = useState<BerichtType>((bericht?.type as BerichtType) ?? "update");
  const [versie, setVersie] = useState(bericht?.versie ?? "");
  const [fout, setFout] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);
  const [tab, setTab] = useState("bewerken");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    setBezig(true);
    const body: BerichtAanmakenIn = {
      titel: titel.trim(),
      inhoud: inhoud.trim(),
      type,
      versie: versie.trim() || null,
    };
    try {
      if (bericht) {
        await updateBericht(bericht.id, body);
      } else {
        await maakBericht(body);
      }
      onDone();
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
    } finally {
      setBezig(false);
    }
  }

  return (
    <form onSubmit={(e) => void onSubmit(e)} className="space-y-4">
      {fout && <Melding type="fout" compact>{fout}</Melding>}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Titel" required>
          <Input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            maxLength={256}
            required
            placeholder="Wat is er veranderd? (max 60 tekens ideaal)"
          />
        </Field>
        <Field label="Versie (optioneel)">
          <Input
            value={versie}
            onChange={(e) => setVersie(e.target.value)}
            maxLength={32}
            placeholder="bijv. v1.3.0 of 2026-08"
          />
        </Field>
      </div>

      <Field label="Type">
        <Select value={type} onChange={(e) => setType(e.target.value as BerichtType)}>
          {TYPEN.map((t) => (
            <option key={t.value} value={t.value}>{t.label}</option>
          ))}
        </Select>
      </Field>

      <div>
        <Tabs
          tabs={[
            {
              key: "bewerken",
              label: "Bewerken",
              content: (
                <Field label="Inhoud (Markdown)" required>
                  <Textarea
                    value={inhoud}
                    onChange={(e) => setInhoud(e.target.value)}
                    rows={6}
                    className="font-mono text-xs"
                    maxLength={10000}
                    required
                    placeholder="Max 2 zinnen — wat is er veranderd en wat betekent dat voor de gebruiker."
                  />
                </Field>
              ),
            },
            {
              key: "preview",
              label: "Preview",
              content: inhoud.trim()
                ? <Markdown tekst={inhoud} />
                : <p className="text-sm text-muted">Schrijf inhoud om een preview te zien.</p>,
            },
          ]}
          active={tab}
          onChange={setTab}
        />
      </div>

      <ButtonRow>
        <Button type="submit" disabled={bezig}>
          {bezig ? "Opslaan…" : bericht ? "Wijzigingen opslaan" : "Concept aanmaken"}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={bezig}>
          Annuleren
        </Button>
      </ButtonRow>
    </form>
  );
}
