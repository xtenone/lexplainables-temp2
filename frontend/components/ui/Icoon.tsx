/** Kleine inline-iconen die tekstkleur en -grootte volgen.
 *
 *  Waarom dit bestaat: de UI gebruikte losse tekens — `▾` voor een uitklapper, `⚠` bij een
 *  waarschuwing, `✓` bij een afgevinkt item, `◇` bij twijfel, `←` voor terug. Die staan geen van
 *  alle in de latin-subset van Fira Sans (`app/fonts.ts`), dus de browser viel terug op het
 *  systeemfont: San Francisco op iOS, Roboto op Android, Segoe op Windows. Andere breedte, ander
 *  gewicht, andere optische grootte — vandaar dat dezelfde kaart op een telefoon net iets anders
 *  oogde dan op een desktop.
 *
 *  Een SVG kent dat probleem niet. Deze zijn `1em` bij `1em` en tekenen met `currentColor`, dus ze
 *  schalen mee met de tekst eromheen en nemen zijn kleur over — precies wat een tekstteken deed,
 *  maar dan overal hetzelfde.
 *
 *  Ze zijn `aria-hidden`: het zijn versieringen bij tekst die de betekenis al draagt. Staat een
 *  icoon alleen (zonder woord ernaast), geef de knop of het element dan zelf een `aria-label`.
 */

interface IcoonProps {
  className?: string;
}

/** Gedeelde vorm: 1em-vierkant, lijntekening in de tekstkleur. */
function svg(pad: React.ReactNode, className = "", extra?: { fill?: boolean }) {
  return (
    <svg
      viewBox="0 0 16 16"
      className={`inline-block h-[1em] w-[1em] shrink-0 ${className}`}
      fill={extra?.fill ? "currentColor" : "none"}
      stroke={extra?.fill ? "none" : "currentColor"}
      strokeWidth={extra?.fill ? undefined : 1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {pad}
    </svg>
  );
}

/** Uitklapper of dropdown. Draai hem met een `rotate-*`-klasse: `-rotate-90` wijst naar links
 *  (terug), `-rotate-180` naar boven (ingeklapt). */
export function ChevronOmlaag({ className = "" }: IcoonProps) {
  return svg(<path d="M4 6l4 4 4-4" />, className);
}

/** Let op — bij een zwevende markering of een teller die aandacht vraagt. */
export function Waarschuwing({ className = "" }: IcoonProps) {
  return svg(
    <>
      <path d="M8 2.5 14.5 13.5h-13L8 2.5Z" />
      <path d="M8 6.5v3.2" />
      <path d="M8 11.8v.01" />
    </>,
    className,
  );
}

/** Afgehandeld, aanwezig, gelukt. */
export function Vinkje({ className = "" }: IcoonProps) {
  return svg(<path d="M3 8.5 6.5 12 13 4.5" />, className);
}

/** Neutraal, onbepaald — er valt niets te melden of niets te controleren. */
export function Cirkel({ className = "" }: IcoonProps) {
  return svg(<circle cx="8" cy="8" r="5.2" />, className);
}

/** Twijfel tussen klassen: de annoteerder zag twee plausibele opties. Bewust een open ruit en geen
 *  uitroepteken — twijfel is geen bezwaar. */
export function Ruit({ className = "" }: IcoonProps) {
  return svg(<path d="M8 2.5 13.5 8 8 13.5 2.5 8Z" />, className);
}
