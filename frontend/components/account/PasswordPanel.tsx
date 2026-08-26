"use client";

import { useState } from "react";
import { signOut } from "next-auth/react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { SettingGroup, SettingList, SettingRow } from "@/components/ui/SettingRow";
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
      // Een wachtwoordwijziging revoket alle sessies (ook op andere apparaten). Log dit apparaat
      // meteen uit en terug naar /login, zodat het een vers token haalt i.p.v. zo dadelijk zelf uit
      // te vliegen bij de herverificatie.
      await signOut({ callbackUrl: "/login" });
    } catch (e) {
      setFout(isApiError(e) ? e.detail : (e as Error).message);
      setBezig(false);
    }
  }

  return (
    <SettingGroup
      titel="Wachtwoord"
      omschrijving="Na het wijzigen word je opnieuw ingelogd; ook andere apparaten verliezen hun sessie."
    >
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
      <form onSubmit={onSubmit}>
        <SettingList>
          <SettingRow label="Huidig wachtwoord" htmlFor="pw-huidig">
            <Input
              id="pw-huidig"
              type="password"
              autoComplete="current-password"
              required
              className="sm:w-64"
              value={huidig}
              onChange={(e) => setHuidig(e.target.value)}
            />
          </SettingRow>
          <SettingRow label="Nieuw wachtwoord" omschrijving="Minimaal 8 tekens." htmlFor="pw-nieuw">
            <Input
              id="pw-nieuw"
              type="password"
              autoComplete="new-password"
              required
              className="sm:w-64"
              value={nieuw}
              onChange={(e) => setNieuw(e.target.value)}
            />
          </SettingRow>
          <SettingRow label="Herhaal nieuw wachtwoord" htmlFor="pw-herhaal">
            <Input
              id="pw-herhaal"
              type="password"
              autoComplete="new-password"
              required
              className="sm:w-64"
              value={herhaling}
              onChange={(e) => setHerhaling(e.target.value)}
            />
          </SettingRow>
        </SettingList>
        <div className="mt-4 flex sm:justify-end">
          <Button type="submit" size="sm" disabled={bezig} className="w-full sm:w-auto">
            {bezig ? "Bezig…" : "Wachtwoord wijzigen"}
          </Button>
        </div>
      </form>
    </SettingGroup>
  );
}
