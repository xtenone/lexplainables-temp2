"use client";

import { useMemo } from "react";

import { jasStyle } from "@/lib/jas";

/** Minimaal element voor highlighting: klasse + letterlijk fragment (+ optioneel id). */
export interface Markeerbaar {
  id?: string;
  klasse: string;
  tekst: string;
}

interface Segment {
  tekst: string;
  klasse?: string;
  id?: string;
}

/** Bepaal niet-overlappende markeringen in `bron`: per fragment de eerste vrije positie (langste
 *  fragmenten eerst, zodat een lang fragment niet door een korter deel wordt opgebroken). */
export function segmenteer(bron: string, elementen: Markeerbaar[]): Segment[] {
  const bezet: { start: number; end: number; klasse: string; id?: string }[] = [];
  const gesorteerd = [...elementen].sort((a, b) => b.tekst.length - a.tekst.length);
  for (const el of gesorteerd) {
    const fragment = el.tekst.trim();
    if (!fragment) continue;
    let van = 0;
    for (;;) {
      const idx = bron.indexOf(fragment, van);
      if (idx === -1) break;
      const eind = idx + fragment.length;
      const overlapt = bezet.some((b) => idx < b.end && eind > b.start);
      if (!overlapt) {
        bezet.push({ start: idx, end: eind, klasse: el.klasse, id: el.id });
        break;
      }
      van = idx + 1;
    }
  }
  bezet.sort((a, b) => a.start - b.start);

  const segmenten: Segment[] = [];
  let pos = 0;
  for (const b of bezet) {
    if (b.start > pos) segmenten.push({ tekst: bron.slice(pos, b.start) });
    segmenten.push({ tekst: bron.slice(b.start, b.end), klasse: b.klasse, id: b.id });
    pos = b.end;
  }
  if (pos < bron.length) segmenten.push({ tekst: bron.slice(pos) });
  return segmenten;
}

export function DocumentPaneel({
  opschrift,
  leden,
  elementen,
  actiefId,
  onKies,
}: {
  opschrift: string;
  leden: string[];
  elementen: Markeerbaar[];
  actiefId?: string;
  onKies?: (id?: string) => void;
}) {
  const bron = useMemo(() => leden.join("\n\n"), [leden]);
  const segmenten = useMemo(() => segmenteer(bron, elementen), [bron, elementen]);

  return (
    <div className="rounded-xl border border-line bg-white p-5">
      {opschrift && <h2 className="mb-3 font-display text-lg font-semibold text-lint">{opschrift}</h2>}
      <p className="whitespace-pre-wrap text-[0.95rem] leading-7 text-ink">
        {segmenten.map((s, i) =>
          s.klasse ? (
            <mark
              key={i}
              onClick={() => onKies?.(s.id)}
              title={s.klasse}
              className={`cursor-pointer rounded px-0.5 ${jasStyle(s.klasse)} ${
                actiefId && s.id === actiefId ? "ring-2 ring-lint" : ""
              }`}
            >
              {s.tekst}
            </mark>
          ) : (
            <span key={i}>{s.tekst}</span>
          ),
        )}
      </p>
    </div>
  );
}
