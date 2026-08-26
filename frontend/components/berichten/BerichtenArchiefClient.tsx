"use client";

import { useEffect, useState } from "react";
import { isApiError, listBerichtenPagina, markeerAllesGelezen } from "@/lib/api";
import type { BerichtenPaginaOut, BerichtType } from "@/lib/types";
import { BerichtBadge } from "@/components/ui/BerichtBadge";
import { Tag } from "@/components/ui/Badge";
import { Skeleton } from "@/components/ui/Skeleton";
import { Markdown } from "@/components/werkplek/Markdown";
import { Pagination } from "@/components/Pagination";

function BerichtArchiefItem({ bericht }: { bericht: BerichtenPaginaOut["items"][number] }) {
  const datum = new Date(bericht.gepubliceerd_op ?? bericht.created).toLocaleDateString("nl-NL", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <article className="rounded-button border border-line bg-paper p-5">
      <div className="flex flex-wrap items-center gap-1.5">
        <BerichtBadge type={bericht.type as BerichtType} />
        {bericht.versie && <Tag>{bericht.versie}</Tag>}
        <span className="text-xs text-faint">{datum}</span>
      </div>
      <h2 className="mt-2 text-base font-semibold text-ink">{bericht.titel}</h2>
      <div className="mt-2 text-sm">
        <Markdown tekst={bericht.inhoud} />
      </div>
    </article>
  );
}

export function BerichtenArchiefClient() {
  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<BerichtenPaginaOut | null>(null);
  const [laden, setLaden] = useState(true);
  const [fout, setFout] = useState<string | null>(null);

  useEffect(() => {
    let stale = false;
    // Bewust synchroon: bij een paginawissel moet de laadindicator meteen aan, vóór de fetch.
    // Dat kost één extra render — de regel waarschuwt daarvoor, hier is het de bedoeling.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLaden(true);
    setFout(null);
    listBerichtenPagina(pagina)
      .then((result) => {
        if (stale) return;
        setData(result);
        if (pagina === 1 && result.items.some((b) => !b.gelezen)) {
          markeerAllesGelezen().catch(() => {});
        }
      })
      .catch((err) => {
        if (!stale) setFout(isApiError(err) ? err.detail : "Kan berichten niet laden.");
      })
      .finally(() => { if (!stale) setLaden(false); });
    return () => { stale = true; };
  }, [pagina]);

  if (laden) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="rounded-button border border-line bg-paper p-5 space-y-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-2/3" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
    );
  }

  if (fout) {
    return <p className="text-sm text-fout">{fout}</p>;
  }

  if (!data || data.items.length === 0) {
    return <p className="text-sm text-muted">Nog geen berichten.</p>;
  }

  const totalPages = Math.ceil(data.totaal / data.per_pagina);

  return (
    <div className="space-y-4">
      {data.items.map((b) => (
        <BerichtArchiefItem key={b.id} bericht={b} />
      ))}
      <Pagination
        page={pagina}
        totalPages={totalPages}
        total={data.totaal}
        pageSize={data.per_pagina}
        onPage={(p) => {
          setPagina(p);
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      />
    </div>
  );
}
