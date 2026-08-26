"use client";

import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { isApiError, stuurFeedback } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { ButtonRow } from "@/components/ui/ButtonRow";
import { Dialog } from "@/components/ui/Dialog";
import { Field, Textarea } from "@/components/ui/Field";
import { Melding } from "@/components/ui/Melding";

type Categorie = "verbeteridee" | "probleemmelding" | "compliment" | "vraag";

const CATEGORIEEN: { waarde: Categorie; label: string }[] = [
  { waarde: "verbeteridee", label: "Verbeteridee" },
  { waarde: "probleemmelding", label: "Probleemmelding" },
  { waarde: "compliment", label: "Compliment" },
  { waarde: "vraag", label: "Vraag" },
];

const MAX = 4000;

/** Feedbackformulier als modaal venster.
 *
 *  Bewust **zonder eigen launcher-knop**: de app-shell heeft geen plek voor een zwevende knop —
 *  die zou over de chat-invoer van de werkplek vallen. De sidebar opent hem vanuit het
 *  gebruikersmenu en bezit dus de open-state. Vormgeving via de gedeelde primitives (`Dialog`,
 *  `Button`, `Field`), zodat knopmaten en focus-trap gelijk lopen met de rest van de app. */
export function FeedbackDialoog({ onSluit }: { onSluit: () => void }) {
  const pathname = usePathname();
  // Het pad bij het openen vastpinnen: navigeert de gebruiker daarna, dan hoort de melding nog bij
  // het scherm waar hij hem schreef.
  const [pagina] = useState(() => pathname ?? "");
  const [categorie, setCategorie] = useState<Categorie>("verbeteridee");
  const [tekst, setTekst] = useState("");
  const [bezig, setBezig] = useState(false);
  const [verzonden, setVerzonden] = useState(false);
  const [fout, setFout] = useState<string | null>(null);
  const eersteInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!verzonden) eersteInputRef.current?.focus();
  }, [verzonden]);

  async function verzend() {
    if (!tekst.trim()) {
      setFout("Vul een bericht in.");
      return;
    }
    setBezig(true);
    setFout(null);
    try {
      await stuurFeedback({ categorie, tekst: tekst.trim(), pagina: pagina || undefined });
      setVerzonden(true);
    } catch (e) {
      setFout(isApiError(e) ? e.detail : "Er is iets misgegaan. Probeer het opnieuw.");
    } finally {
      setBezig(false);
    }
  }

  return (
    // `compact`: een formulier met drie velden hoort niet in een venster van 42rem met een halve
    // pagina wit onder de verzendknop.
    <Dialog label="Feedback geven" variant="compact" onSluit={onSluit}>
      {/* Dezelfde kop als het instellingenvenster en de voorwaarden: titel links, kruisje rechts.
          Hier ontbrak dat kruisje — sluiten kon alleen via Escape, de achtergrond of de knop onderin,
          en op een telefoon (waar de dialoog het scherm vult) is die rechterbovenhoek nu juist waar
          iedereen als eerste kijkt. */}
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5 pt-[max(0.875rem,env(safe-area-inset-top))]">
        <h2 className="font-display text-base font-semibold text-lint">Feedback geven</h2>
        <button
          type="button"
          onClick={onSluit}
          aria-label="Feedback sluiten"
          className="focus-ring -mr-1 rounded-kaart p-1.5 text-muted transition-colors hover:bg-surface hover:text-ink"
        >
          <svg viewBox="0 0 20 20" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            <path d="M5 5l10 10M15 5L5 15" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <div className="flex min-h-0 flex-col gap-4 overflow-y-auto p-6">
        {verzonden ? (
          <div className="flex flex-col items-center gap-3 py-6 text-center">
            <p className="text-base font-semibold text-lint">Bedankt voor je feedback</p>
            <p className="text-sm text-muted">
              Je bericht is ontvangen en wordt meegenomen in de doorontwikkeling.
            </p>
            <Button className="mt-2" onClick={onSluit}>
              Sluiten
            </Button>
          </div>
        ) : (
          <>
            <fieldset>
              <legend className="mb-2 text-sm font-medium text-ink">Categorie</legend>
              <div className="grid grid-cols-2 gap-2">
                {CATEGORIEEN.map(({ waarde, label }, i) => (
                  <label
                    key={waarde}
                    className={`flex min-h-[40px] cursor-pointer items-center gap-2 rounded-kaart border px-3 py-2 text-sm transition-colors coarse:min-h-[48px] ${
                      categorie === waarde
                        ? "border-lint bg-lint/5 font-medium text-lint"
                        : "border-line bg-paper text-ink hover:bg-surface"
                    }`}
                  >
                    <input
                      ref={i === 0 ? eersteInputRef : undefined}
                      type="radio"
                      name="categorie"
                      value={waarde}
                      checked={categorie === waarde}
                      onChange={() => setCategorie(waarde)}
                      className="accent-lint"
                    />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>

            <Field label="Bericht" required hint={`${tekst.length}/${MAX} tekens`}>
              <Textarea
                value={tekst}
                onChange={(e) => setTekst(e.target.value)}
                placeholder="Beschrijf je idee, probleem of vraag…"
                rows={5}
                maxLength={MAX}
                disabled={bezig}
              />
            </Field>

            <p className="text-xs text-muted">
              Meegestuurd als context: <span className="font-mono">{pagina || "onbekend"}</span>
            </p>

            {fout && <Melding type="fout" compact>{fout}</Melding>}

            <ButtonRow>
              <Button onClick={() => void verzend()} disabled={bezig || !tekst.trim()}>
                {bezig ? "Verzenden…" : "Verzenden"}
              </Button>
              <Button variant="ghost" onClick={onSluit} disabled={bezig}>
                Annuleren
              </Button>
            </ButtonRow>
          </>
        )}
      </div>
    </Dialog>
  );
}
