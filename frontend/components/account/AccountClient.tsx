"use client";

import { useCallback, useEffect, useState } from "react";
import QRCode from "qrcode";
import { Vinkje } from "@/components/ui/Icoon";
import { Button } from "@/components/ui/Button";
import { SettingGroup, SettingList, SettingRow } from "@/components/ui/SettingRow";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { Tag } from "@/components/ui/Badge";
import { activate2fa, begin2fa, disable2fa, getAccount, isApiError } from "@/lib/api";
import type { MeAccount } from "@/lib/types";

/** Haal het base32-secret uit de otpauth://-URI voor handmatige invoer in de authenticator-app. */
function secretUit(uri: string): string {
  try {
    return new URL(uri).searchParams.get("secret") ?? "";
  } catch {
    return "";
  }
}

export function AccountClient() {
  const [account, setAccount] = useState<MeAccount | null>(null);
  const [fout, setFout] = useState<string | null>(null);
  // Lopende 2FA-koppeling: de QR/secret + het in te voeren code-veld.
  const [koppeling, setKoppeling] = useState<{ uri: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  // Bevestigingsformulier bij het uitschakelen van 2FA.
  const [uitschakelCode, setUitschakelCode] = useState("");
  const [bezig, setBezig] = useState(false);

  const laad = useCallback(async () => {
    setFout(null);
    try {
      setAccount(await getAccount());
    } catch (e) {
      setFout(isApiError(e) ? `${e.detail} (${e.status})` : (e as Error).message);
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

  async function onStart() {
    setFout(null);
    setBezig(true);
    try {
      const { otpauth_uri } = await begin2fa();
      const qr = await QRCode.toDataURL(otpauth_uri, { margin: 1, width: 200 });
      setKoppeling({ uri: otpauth_uri, qr });
      setCode("");
    } catch (e) {
      melden(e);
    } finally {
      setBezig(false);
    }
  }

  async function onBevestig(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    setBezig(true);
    try {
      await activate2fa(code.trim());
      setKoppeling(null);
      setCode("");
      await laad();
    } catch (e) {
      melden(e);
    } finally {
      setBezig(false);
    }
  }

  async function onUitschakelen(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    setBezig(true);
    try {
      await disable2fa(uitschakelCode.trim());
      setUitschakelCode("");
      await laad();
    } catch (e) {
      melden(e);
    } finally {
      setBezig(false);
    }
  }

  return (
    <SettingGroup
      titel="Beveiliging"
      omschrijving="Tweestapsverificatie is optioneel. Staat die aan, dan vraagt het inloggen om een code uit je authenticator-app."
    >
      {fout && (
        <Melding type="fout" className="mb-3">
          {fout}
        </Melding>
      )}

      {account && (
        <div>
          <SettingList>
            <SettingRow label="Account" omschrijving={account.email}>
              <span className="text-sm text-ink">{account.userid}</span>
              <Tag>{account.role}</Tag>
            </SettingRow>
            <SettingRow
              label="Tweestapsverificatie"
              omschrijving={account.totp_enabled ? "Ingeschakeld." : "Uitgeschakeld."}
            >
              {account.totp_enabled ? <Tag><span className="inline-flex items-center gap-1">2FA <Vinkje /></span></Tag> : <Tag>2FA uit</Tag>}
            </SettingRow>
          </SettingList>

          {account.totp_enabled ? (
            <form onSubmit={onUitschakelen} className="mt-4 space-y-3">
              <p className="text-sm text-muted">
                Voer een geldige code uit je authenticator-app in om tweestapsverificatie uit te schakelen.
              </p>
              <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
                <Field label="Code uit de app" hint="6 cijfers">
                  <Input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    required
                    value={uitschakelCode}
                    onChange={(e) => setUitschakelCode(e.target.value)}
                  />
                </Field>
                <Button type="submit" size="sm" variant="danger" disabled={bezig} className="w-full sm:w-auto">
                  2FA uitschakelen
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setUitschakelCode("")}
                  disabled={bezig}
                  className="w-full sm:w-auto"
                >
                  Annuleren
                </Button>
              </div>
            </form>
          ) : koppeling ? (
            <div className="mt-4 space-y-3">
              <p className="text-sm text-muted">
                Scan de QR-code met je authenticator-app (of voer de sleutel handmatig in) en
                bevestig met de getoonde 6-cijferige code.
              </p>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={koppeling.qr} alt="QR-code voor 2FA" width={200} height={200} className="rounded border border-line" />
              <p className="text-xs text-muted">
                Handmatige sleutel:{" "}
                <code className="rounded bg-surface px-1.5 py-0.5 font-mono text-xs">{secretUit(koppeling.uri)}</code>
              </p>
              <form onSubmit={onBevestig} className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
                <Field label="Code uit de app" hint="6 cijfers">
                  <Input
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    required
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                  />
                </Field>
                <Button type="submit" size="sm" disabled={bezig} className="w-full sm:w-auto">
                  Bevestigen
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setKoppeling(null)}
                  disabled={bezig}
                  className="w-full sm:w-auto"
                >
                  Annuleren
                </Button>
              </form>
            </div>
          ) : (
            <div className="mt-4 flex sm:justify-end">
              <Button size="sm" onClick={onStart} disabled={bezig} className="w-full sm:w-auto">
                2FA inschakelen
              </Button>
            </div>
          )}
        </div>
      )}
    </SettingGroup>
  );
}
