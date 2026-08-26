"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";
import { loginVerify } from "@/lib/api";
import { veiligPad } from "@/lib/url";

export function LoginClient() {
  const router = useRouter();
  const params = useSearchParams();
  const [userid, setUserid] = useState("");
  const [password, setPassword] = useState("");
  const [onthouden, setOnthouden] = useState(false);
  const [fout, setFout] = useState<string | null>(null);
  const [bezig, setBezig] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFout(null);
    setBezig(true);
    try {
      // Pre-check: kloppen de gegevens, en is 2FA nodig? (zet zelf nog geen sessie)
      const check = await loginVerify(userid, password);

      if (check.code === "rate") {
        setFout("Te veel inlogpogingen. Wacht even en probeer het opnieuw.");
        return;
      }
      if (check.code === "totp_required") {
        // 2FA nodig én dit apparaat is niet (meer) vertrouwd → naar het aparte 2FA-scherm. Draag de
        // niet-gevoelige userid + de remember-keuze + callbackUrl mee; het login-ticket (httpOnly
        // cookie) draagt het wachtwoord-bewijs, zodat het wachtwoord het geheugen niet verlaat.
        sessionStorage.setItem("wa_login_userid", userid);
        sessionStorage.setItem("wa_login_remember", onthouden ? "1" : "0");
        const cb = params.get("callbackUrl");
        router.push(cb ? `/login/2fa?callbackUrl=${encodeURIComponent(cb)}` : "/login/2fa");
        return;
      }
      if (!check.ok) {
        setFout("Onjuiste gebruikersnaam of wachtwoord.");
        return;
      }

      // Gegevens kloppen (geen 2FA, of een vertrouwd apparaat) → sessie opzetten via Auth.js.
      const res = await signIn("credentials", {
        redirect: false,
        userid,
        password,
        remember: onthouden ? "1" : "0",
      });
      if (res?.error) {
        setFout("Inloggen mislukt. Probeer het opnieuw.");
        return;
      }
      // Harde navigatie (niet router.push): de bestemming kan door de disclaimer-gate in
      // auth.config.ts naar /disclaimer omgeleid worden. Een router.push (soft navigation)
      // gecombineerd met een middleware-redirect laat de Next.js-router in de war achter — de
      // pagina laadt dan wel, maar eigen client-side navigatie (knoppen, links) erop reageert
      // niet meer tot een handmatige refresh. Een window.location-navigatie doorloopt de
      // redirect zoals een normale paginalaad (en dat is precies wat een refresh ook doet).
      window.location.href = veiligPad(params.get("callbackUrl"), window.location.origin);
    } finally {
      setBezig(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {fout && <Melding type="fout">{fout}</Melding>}
      <Field label="Gebruikersnaam" required>
        <Input
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          required
          value={userid}
          onChange={(e) => setUserid(e.target.value)}
        />
      </Field>
      <Field label="Wachtwoord" required>
        <Input
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </Field>

      <label className="flex items-start gap-2 text-sm text-ink">
        <input
          type="checkbox"
          className="mt-0.5 h-4 w-4 accent-lint"
          checked={onthouden}
          onChange={(e) => setOnthouden(e.target.checked)}
        />
        <span>
          Ingelogd blijven op dit apparaat
          <span className="block text-xs text-muted">
            30 dagen ingelogd blijven en 2FA overslaan op dit apparaat.
          </span>
        </span>
      </label>

      <Button type="submit" disabled={bezig} className="w-full">
        {bezig ? "Bezig met inloggen…" : "Inloggen"}
      </Button>
    </form>
  );
}
