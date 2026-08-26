"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";

export function SetupClient() {
  const [userid, setUserid] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [herhaling, setHerhaling] = useState("");
  const [fout, setFout] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    if (password.length < 8) {
      setFout("Kies een wachtwoord van minimaal 8 tekens.");
      return;
    }
    if (password !== herhaling) {
      setFout("De wachtwoorden komen niet overeen.");
      return;
    }
    setBezig(true);
    try {
      const res = await fetch("/api/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ userid, email, password }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        setFout(
          res.status === 409
            ? "Registratie is al gesloten — er bestaat al een account."
            : `Aanmaken mislukt${body?.detail ? `: ${body.detail}` : ""}.`,
        );
        return;
      }
      // Direct inloggen met de zojuist aangemaakte beheerder. Harde navigatie (niet router.push):
      // "/" kan door de disclaimer-gate omgeleid worden naar /disclaimer, en dat combineert niet
      // goed met een soft router.push (zie de toelichting in LoginClient.tsx).
      const login = await signIn("credentials", { redirect: false, userid, password });
      window.location.href = login?.error ? "/login" : "/";
    } catch {
      // Zie LoginClient: een transportfout is geen antwoord en viel dus buiten alle afhandeling.
      setFout("Aanmaken lukt nu niet — de dienst is niet bereikbaar. Probeer het zo opnieuw.");
    } finally {
      setBezig(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {fout && <Melding type="fout">{fout}</Melding>}
      <Field label="Gebruikersnaam" hint="3–64 tekens: letters, cijfers, . _ -" required>
        <Input
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          required
          value={userid}
          onChange={(e) => setUserid(e.target.value)}
        />
      </Field>
      <Field label="E-mailadres" required>
        <Input
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
      </Field>
      <Field label="Wachtwoord" hint="minimaal 8 tekens" required>
        <Input
          type="password"
          autoComplete="new-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>
      <Field label="Wachtwoord herhalen" required>
        <Input
          type="password"
          autoComplete="new-password"
          required
          value={herhaling}
          onChange={(e) => setHerhaling(e.target.value)}
        />
      </Field>
      <Button type="submit" disabled={bezig} className="w-full">
        {bezig ? "Bezig…" : "Beheerder aanmaken"}
      </Button>
    </form>
  );
}
