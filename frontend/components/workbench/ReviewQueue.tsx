"use client";

import { useState } from "react";

import { JAS_KLASSEN, jasStyle } from "@/lib/jas";
import type { AnnotatieElement, BeslissingInvoer, ReviewReason } from "@/lib/types";

const REDENEN: { waarde: ReviewReason; label: string }[] = [
  { waarde: "verkeerde_klasse", label: "verkeerde klasse" },
  { waarde: "bron_gemist", label: "bron gemist" },
  { waarde: "tekst", label: "tekst onjuist" },
  { waarde: "interpretatie", label: "interpretatie" },
  { waarde: "onvoldoende_context", label: "onvoldoende context" },
  { waarde: "anders", label: "anders" },
];

const LIFECYCLE_LABEL: Record<string, string> = {
  voorgesteld: "voorgesteld",
  critic_checked: "te reviewen",
  human_approved: "akkoord",
  edited: "aangepast",
  rejected: "verworpen",
};

const AANDACHT: Record<string, { emoji: string; label: string }> = {
  groen: { emoji: "🟢", label: "groen — geen bezwaar" },
  geel: { emoji: "🟡", label: "geel — even kijken" },
  rood: { emoji: "🔴", label: "rood — waarschijnlijk fout" },
};

type Actie = "reject" | "edit" | "comment" | null;

function DecisionCard({
  el,
  actief,
  onKies,
  onBeslissing,
}: {
  el: AnnotatieElement;
  actief: boolean;
  onKies: () => void;
  onBeslissing: (req: BeslissingInvoer) => Promise<void>;
}) {
  const [actie, setActie] = useState<Actie>(null);
  const [reden, setReden] = useState<ReviewReason>("interpretatie");
  const [comment, setComment] = useState("");
  const [klasse, setKlasse] = useState(el.klasse);
  const [toelichting, setToelichting] = useState(el.toelichting);
  const [bezig, setBezig] = useState(false);

  // "beslist" = de mens heeft al een besluit genomen; `voorgesteld`/`critic_checked` zijn nog te reviewen.
  const beslist = ["human_approved", "edited", "rejected"].includes(el.lifecycle);

  async function verstuur(req: BeslissingInvoer) {
    setBezig(true);
    try {
      await onBeslissing(req);
      setActie(null);
    } finally {
      setBezig(false);
    }
  }

  return (
    <div
      onClick={onKies}
      className={`rounded-xl border bg-white p-3 transition ${
        actief ? "border-lint ring-1 ring-lint" : "border-line"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1.5">
          {el.aandacht && (
            <span title={el.critic || AANDACHT[el.aandacht]?.label} aria-label={AANDACHT[el.aandacht]?.label}>
              {AANDACHT[el.aandacht]?.emoji}
            </span>
          )}
          <span className={`rounded px-2 py-0.5 text-xs font-semibold ${jasStyle(el.klasse)}`}>{el.klasse}</span>
        </span>
        <span className="text-[0.65rem] uppercase tracking-wide text-muted">
          {LIFECYCLE_LABEL[el.lifecycle] ?? el.lifecycle}
          {el.lid ? ` · lid ${el.lid}` : ""}
        </span>
      </div>
      <p className="mt-1.5 text-sm text-ink">“{el.tekst}”</p>
      {el.toelichting && <p className="mt-1 text-xs text-muted">{el.toelichting}</p>}
      {el.critic && <p className="mt-1 text-xs italic text-muted">Critic: {el.critic}</p>}
      {el.alternatieven.length > 0 &&
        (beslist ? (
          <p className="mt-1 text-xs text-muted">Twijfel: {el.alternatieven.map((a) => a.klasse).join(", ")}</p>
        ) : (
          <div className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted" onClick={(e) => e.stopPropagation()}>
            <span>Twijfel — kies om te wijzigen:</span>
            {el.alternatieven.map((a) => (
              <button
                key={a.klasse}
                title={a.motivatie}
                onClick={() => {
                  setKlasse(a.klasse);
                  setReden("verkeerde_klasse");
                  setActie("edit");
                }}
                className={`rounded px-1.5 py-0.5 text-xs font-medium ${jasStyle(a.klasse)} hover:ring-1 hover:ring-lint`}
              >
                {a.klasse}
              </button>
            ))}
          </div>
        ))}

      {!beslist && actie === null && (
        <div className="mt-2 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
          <button
            disabled={bezig}
            onClick={() => verstuur({ type: "approve" })}
            className="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
          >
            Akkoord
          </button>
          <button
            onClick={() => setActie("edit")}
            className="rounded bg-sky-600 px-2 py-1 text-xs font-medium text-white hover:bg-sky-700"
          >
            Aanpassen
          </button>
          <button
            onClick={() => setActie("reject")}
            className="rounded bg-rose-600 px-2 py-1 text-xs font-medium text-white hover:bg-rose-700"
          >
            Verwerpen
          </button>
          <button
            onClick={() => setActie("comment")}
            className="rounded border border-line px-2 py-1 text-xs font-medium text-ink hover:bg-surface"
          >
            Opmerking
          </button>
        </div>
      )}

      {actie === "reject" && (
        <div className="mt-2 space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <RedenSelect reden={reden} setReden={setReden} />
          <div className="flex gap-1.5">
            <button
              disabled={bezig}
              onClick={() => verstuur({ type: "reject", review_reason: reden })}
              className="rounded bg-rose-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Verwerpen
            </button>
            <AnnuleerKnop onClick={() => setActie(null)} />
          </div>
        </div>
      )}

      {actie === "edit" && (
        <div className="mt-2 space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <select
            value={klasse}
            onChange={(e) => setKlasse(e.target.value)}
            className="w-full rounded border border-line px-2 py-1 text-xs"
          >
            {JAS_KLASSEN.map((k) => (
              <option key={k} value={k}>
                {k}
              </option>
            ))}
          </select>
          <input
            value={toelichting}
            onChange={(e) => setToelichting(e.target.value)}
            placeholder="Toelichting"
            className="w-full rounded border border-line px-2 py-1 text-xs"
          />
          <RedenSelect reden={reden} setReden={setReden} />
          <div className="flex gap-1.5">
            <button
              disabled={bezig}
              onClick={() =>
                verstuur({ type: "edit", review_reason: reden, wijziging: { klasse, toelichting } })
              }
              className="rounded bg-sky-600 px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Opslaan
            </button>
            <AnnuleerKnop onClick={() => setActie(null)} />
          </div>
        </div>
      )}

      {actie === "comment" && (
        <div className="mt-2 space-y-1.5" onClick={(e) => e.stopPropagation()}>
          <input
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            placeholder="Opmerking"
            className="w-full rounded border border-line px-2 py-1 text-xs"
          />
          <div className="flex gap-1.5">
            <button
              disabled={bezig || !comment.trim()}
              onClick={() => verstuur({ type: "comment", comment })}
              className="rounded bg-lint px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
            >
              Plaatsen
            </button>
            <AnnuleerKnop onClick={() => setActie(null)} />
          </div>
        </div>
      )}
    </div>
  );
}

function RedenSelect({ reden, setReden }: { reden: ReviewReason; setReden: (r: ReviewReason) => void }) {
  return (
    <select
      value={reden}
      onChange={(e) => setReden(e.target.value as ReviewReason)}
      className="w-full rounded border border-line px-2 py-1 text-xs"
    >
      {REDENEN.map((r) => (
        <option key={r.waarde} value={r.waarde}>
          {r.label}
        </option>
      ))}
    </select>
  );
}

function AnnuleerKnop({ onClick }: { onClick: () => void }) {
  return (
    <button onClick={onClick} className="rounded border border-line px-2 py-1 text-xs text-muted hover:bg-surface">
      Annuleren
    </button>
  );
}

export function ReviewQueue({
  elementen,
  actiefId,
  onKies,
  onBeslissing,
}: {
  elementen: AnnotatieElement[];
  actiefId?: string;
  onKies: (id?: string) => void;
  onBeslissing: (elementId: string, req: BeslissingInvoer) => Promise<void>;
}) {
  const telling = elementen.reduce<Record<string, number>>((acc, el) => {
    acc[el.lifecycle] = (acc[el.lifecycle] ?? 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3 text-xs text-muted">
        <span>{elementen.length} elementen</span>
        {(telling.voorgesteld ?? 0) + (telling.critic_checked ?? 0) > 0 ? (
          <span>🟡 {(telling.voorgesteld ?? 0) + (telling.critic_checked ?? 0)} te reviewen</span>
        ) : null}
        {telling.human_approved ? <span>🟢 {telling.human_approved} akkoord</span> : null}
        {telling.rejected ? <span>🔴 {telling.rejected} verworpen</span> : null}
      </div>
      {elementen.map((el) => (
        <DecisionCard
          key={el.id}
          el={el}
          actief={el.id === actiefId}
          onKies={() => onKies(el.id)}
          onBeslissing={(req) => onBeslissing(el.id, req)}
        />
      ))}
    </div>
  );
}
