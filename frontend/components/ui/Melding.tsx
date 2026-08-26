import type { ReactNode } from "react";

// Meldingscomponent in de Rijkshuisstijl (zie interactie.png): een gevulde, lichtgekleurde balk
// met een groot massief-gekleurd icoon links en zwarte tekst. Vier functionele types, alle kleuren
// via de tokens uit globals.css / tailwind.config (geen losse hex). De `compact`-variant is voor
// kleine inline-meldingen (bv. twijfel/let-op naast een analyse-item).

export type MeldingType = "fout" | "waarschuwing" | "bevestiging" | "uitleg";

const STIJL: Record<MeldingType, { bg: string; icoon: string }> = {
  fout: { bg: "bg-fout/10", icoon: "text-fout" },
  waarschuwing: { bg: "bg-waarschuwing/10", icoon: "text-waarschuwing" },
  bevestiging: { bg: "bg-succes/10", icoon: "text-succes" },
  uitleg: { bg: "bg-info/10", icoon: "text-info" },
};

function Icoon({ type, className }: { type: MeldingType; className: string }) {
  const klasse = `${className} ${STIJL[type].icoon} shrink-0`;
  switch (type) {
    case "fout":
      // Rode cirkel met wit kruis.
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={klasse}>
          <circle cx="12" cy="12" r="11" fill="currentColor" />
          <path
            d="M8.2 8.2l7.6 7.6M15.8 8.2l-7.6 7.6"
            className="stroke-paper"
            strokeWidth="2.4"
            strokeLinecap="round"
            fill="none"
          />
        </svg>
      );
    case "waarschuwing":
      // Gele driehoek met (donker) uitroepteken — wit haalt op #E17000 net geen AA-contrast.
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={klasse}>
          <path
            d="M12 3.2 22.2 20.4H1.8Z"
            fill="currentColor"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinejoin="round"
          />
          <path d="M12 9.2v4.4" className="stroke-ink" strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="12" cy="17" r="1.3" className="fill-ink" />
        </svg>
      );
    case "bevestiging":
      // Groen afgerond vierkant met witte vink.
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={klasse}>
          <rect x="2" y="2" width="20" height="20" rx="4" fill="currentColor" />
          <path
            d="M7 12.4l3.2 3.4L17 8.6"
            className="stroke-paper"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      );
    case "uitleg":
      // Blauw afgerond vierkant met witte "i".
      return (
        <svg viewBox="0 0 24 24" aria-hidden="true" className={klasse}>
          <rect x="2" y="2" width="20" height="20" rx="4" fill="currentColor" />
          <circle cx="12" cy="7.4" r="1.5" className="fill-paper" />
          <path d="M12 11v6" className="stroke-paper" strokeWidth="2.2" strokeLinecap="round" />
        </svg>
      );
  }
}

export function Melding({
  type,
  titel,
  compact = false,
  className = "",
  children,
}: {
  type: MeldingType;
  /** Optionele vetgedrukte kop boven de inhoud. */
  titel?: string;
  /** Kleine inline-variant: klein icoon, krappere padding, kleinere tekst. */
  compact?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const isFout = type === "fout";
  return (
    <div
      role={isFout ? "alert" : "status"}
      aria-live={isFout ? "assertive" : "polite"}
      className={`flex items-start rounded-md text-ink ${STIJL[type].bg} ${
        compact ? "gap-2 px-3 py-2 text-sm" : "gap-3 px-4 py-3"
      } ${className}`}
    >
      <Icoon type={type} className={compact ? "mt-0.5 h-4 w-4" : "h-7 w-7"} />
      <div className="min-w-0 flex-1">
        {titel && <p className="font-medium">{titel}</p>}
        {children}
      </div>
    </div>
  );
}
