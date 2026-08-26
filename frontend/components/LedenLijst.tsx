import type { Lid } from "@/lib/types";
import { Card } from "@/components/ui/Card";
import { bronHref } from "@/lib/url";

// Toont de letterlijke wettekst per lid (brongetrouw). Eén bron voor zowel het eindrapport
// (RapportView) als de review-context (ReviewPanel), zodat de weergave niet uiteenloopt.
export function LedenLijst({ leden }: { leden: Lid[] }) {
  return (
    <div className="space-y-3">
      {leden.map((l) => {
        const href = bronHref(l.bronreferentie);
        return (
        <Card key={l.lid} className="p-4">
          <div className="flex items-baseline justify-between">
            <span className="font-mono text-xs text-faint">lid {l.lid}</span>
            {href ? (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-xs text-link hover:underline"
              >
                bron ↗
              </a>
            ) : l.bronreferentie ? (
              <span className="font-mono text-xs text-faint">{l.bronreferentie}</span>
            ) : null}
          </div>
          <p className="mt-1 break-words font-display text-[15px] leading-relaxed text-ink">{l.tekst}</p>
        </Card>
        );
      })}
    </div>
  );
}
