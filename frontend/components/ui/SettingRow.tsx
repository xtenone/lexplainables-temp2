import type { ReactNode } from "react";

/** Eén instelling: label (met eventueel een toelichting) links, de bediening rechts.
 *
 *  De vorm van een instellingenscherm, niet die van een formulier: geen kaders per veld, alleen een
 *  dunne scheidingslijn tussen de rijen (zet `divide-y divide-line` op de omhullende lijst). Op smal
 *  scherm zakt de bediening onder het label, zodat er niets in de verdrukking komt. */
export function SettingRow({
  label,
  omschrijving,
  htmlFor,
  children,
}: {
  label: ReactNode;
  omschrijving?: ReactNode;
  /** Maakt het label klikbaar voor het veld ernaast. */
  htmlFor?: string;
  children?: ReactNode;
}) {
  const Label = htmlFor ? "label" : "span";
  return (
    <div className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <div className="min-w-0">
        <Label htmlFor={htmlFor} className="block text-sm font-medium text-ink">
          {label}
        </Label>
        {omschrijving && <p className="mt-0.5 text-[0.8125rem] leading-snug text-muted">{omschrijving}</p>}
      </div>
      {children && <div className="flex shrink-0 items-center gap-2 sm:justify-end">{children}</div>}
    </div>
  );
}

/** Lijst van instellingen met scheidingslijnen ertussen. */
export function SettingList({ children }: { children: ReactNode }) {
  return <div className="divide-y divide-line">{children}</div>;
}

/** Kop boven een groep instellingen (de tabnaam, zoals "Algemeen" in het voorbeeld). */
export function SettingGroup({
  titel,
  omschrijving,
  count,
  children,
}: {
  titel: string;
  omschrijving?: string;
  /** Aantal items, voor lijstgroepen (gebruikers, tokens, profielen). */
  count?: number;
  children: ReactNode;
}) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="flex items-baseline gap-2 font-display text-base font-semibold text-lint">
        {titel}
        {count !== undefined && <span className="font-mono text-xs font-normal text-faint">{count}</span>}
      </h3>
      {omschrijving && <p className="mt-1 text-[0.8125rem] leading-snug text-muted">{omschrijving}</p>}
      <div className="mt-2">{children}</div>
    </section>
  );
}
