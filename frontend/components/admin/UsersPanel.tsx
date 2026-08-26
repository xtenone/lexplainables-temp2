"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Card, Section } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import {
  createUser,
  deleteUser,
  isApiError,
  listUsers,
  patchUser,
  resetUserPassword,
} from "@/lib/api";
import type { Role, UserOut } from "@/lib/types";

export function UsersPanel() {
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  const [nieuwUserid, setNieuwUserid] = useState("");
  const [nieuwEmail, setNieuwEmail] = useState("");
  const [nieuwRol, setNieuwRol] = useState<Role>("analist");
  // Eenmalig getoond tijdelijk wachtwoord (na aanmaken of resetten).
  const [tijdelijk, setTijdelijk] = useState<{ userid: string; wachtwoord: string } | null>(null);

  const laad = useCallback(async () => {
    setFout(null);
    try {
      setUsers(await listUsers());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
      setUsers([]);
    }
  }, []);

  useEffect(() => {
    laad();
  }, [laad]);

  function melden(e: unknown) {
    setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
  }

  async function onAanmaken(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    try {
      const res = await createUser(nieuwUserid.trim(), nieuwEmail.trim(), nieuwRol);
      setTijdelijk({ userid: res.userid, wachtwoord: res.temp_password });
      setNieuwUserid("");
      setNieuwEmail("");
      setNieuwRol("analist");
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  async function onRol(u: UserOut, role: Role) {
    try {
      await patchUser(u.userid, { role });
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  async function onActief(u: UserOut) {
    try {
      await patchUser(u.userid, { active: !u.active });
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  async function onReset(u: UserOut) {
    try {
      const res = await resetUserPassword(u.userid);
      setTijdelijk({ userid: res.userid, wachtwoord: res.temp_password });
    } catch (e) {
      melden(e);
    }
  }

  async function onVerwijder(u: UserOut) {
    if (!confirm(`Gebruiker "${u.userid}" verwijderen?`)) return;
    try {
      await deleteUser(u.userid);
      await laad();
    } catch (e) {
      melden(e);
    }
  }

  return (
    <Section title="Gebruikers" count={users?.length} subtitle="Toegang tot de webapp">
      {fout && (
        <Melding type="fout" className="mb-3">
          {fout}
        </Melding>
      )}

      {tijdelijk && (
        <Melding type="waarschuwing" titel="Tijdelijk wachtwoord — noteer dit nu" className="mb-3">
          <p className="text-sm">
            Voor <span className="font-medium">{tijdelijk.userid}</span>:{" "}
            <code className="rounded bg-paper px-1.5 py-0.5 font-mono text-sm">{tijdelijk.wachtwoord}</code>
          </p>
          <p className="mt-1 text-xs text-muted">
            Dit wachtwoord wordt niet opnieuw getoond. Deel het veilig; de gebruiker logt er meteen mee in.
          </p>
          <ButtonRow align="start" className="mt-2">
            <Button size="sm" variant="secondary" onClick={() => setTijdelijk(null)}>
              Sluiten
            </Button>
          </ButtonRow>
        </Melding>
      )}

      <form onSubmit={onAanmaken} className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
        <Field label="Gebruikersnaam">
          <Input
            type="text"
            required
            autoCapitalize="none"
            placeholder="jdoe"
            value={nieuwUserid}
            onChange={(e) => setNieuwUserid(e.target.value)}
          />
        </Field>
        <div className="min-w-[14rem] flex-1">
          <Field label="E-mailadres">
            <Input
              type="email"
              required
              placeholder="naam@belastingdienst.nl"
              value={nieuwEmail}
              onChange={(e) => setNieuwEmail(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Rol">
          <Select value={nieuwRol} onChange={(e) => setNieuwRol(e.target.value as Role)}>
            <option value="analist">analist</option>
            <option value="beheerder">beheerder</option>
          </Select>
        </Field>
        <Button type="submit" className="w-full sm:w-auto">Gebruiker toevoegen</Button>
      </form>

      {users === null ? (
        <p className="text-sm text-muted">Laden…</p>
      ) : users.length === 0 ? (
        <p className="text-sm text-muted">Nog geen gebruikers.</p>
      ) : (
        <div className="space-y-3">
          {users.map((u) => (
            <Card key={u.userid} className="p-4">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-display font-semibold text-ink">{u.userid}</span>
                <span className="text-sm text-muted">{u.email}</span>
                <Tag>{u.role}</Tag>
                {u.totp_enabled && <Tag>2FA ✓</Tag>}
                {!u.active && (
                  <span className="inline-flex items-center rounded-full border border-fout/40 bg-fout/10 px-2.5 py-0.5 text-xs font-medium text-fout">
                    gedeactiveerd
                  </span>
                )}
              </div>
              <ButtonRow align="start" className="mt-3">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => onRol(u, u.role === "beheerder" ? "analist" : "beheerder")}
                >
                  {u.role === "beheerder" ? "Maak analist" : "Maak beheerder"}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => onActief(u)}>
                  {u.active ? "Deactiveren" : "Activeren"}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => onReset(u)}>
                  Wachtwoord resetten
                </Button>
                <Button size="sm" variant="danger" onClick={() => onVerwijder(u)}>
                  Verwijderen
                </Button>
              </ButtonRow>
            </Card>
          ))}
        </div>
      )}
    </Section>
  );
}
