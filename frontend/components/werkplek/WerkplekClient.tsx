"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Markdown } from "@/components/werkplek/Markdown";
import { DocumentLijst } from "@/components/workbench/DocumentLijst";
import { DocumentPaneel } from "@/components/workbench/DocumentPaneel";
import { ReviewQueue } from "@/components/workbench/ReviewQueue";
import {
  annoteerAgentStream,
  beslis,
  haalArtikelGraaf,
  haalDocument,
  isApiError,
  lijstDocumenten,
  listWetten,
  maakDocument,
  verwijderDocument,
  zetElementen,
} from "@/lib/api";
import type {
  AgentDoel,
  AnnotatieDocument,
  BeslissingInvoer,
  Bron,
  DocumentSamenvatting,
  GraafArtikel,
  OntbrekendItem,
  VoorstelElement,
  WetChoice,
} from "@/lib/types";
import { jasStyle } from "@/lib/jas";
import { wettenOverheidHref } from "@/lib/url";

type Item =
  | { id: string; type: "user"; tekst: string }
  | { id: string; type: "antwoord"; tekst: string; denk?: string; bronnen?: Bron[] }
  | { id: string; type: "annotatie"; slug: string; ontbrekend?: OntbrekendItem[] };

const SESSIE_KEY = "wa_werkplek_sessie";

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function foutTekst(e: unknown): string {
  if (isApiError(e)) return e.detail;
  return (e as Error)?.message ?? "Er ging iets mis.";
}

function sessie(): string {
  try {
    const bestaand = localStorage.getItem(SESSIE_KEY);
    if (bestaand) return bestaand;
    const id = `web-${crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`}`;
    localStorage.setItem(SESSIE_KEY, id);
    return id;
  } catch {
    return `web-${Date.now()}`;
  }
}

function ledenVan(info: GraafArtikel): string[] {
  return info.leden_teksten.map((l) => (l.lid ? `${l.lid}. ${l.tekst}` : l.tekst)).filter(Boolean);
}

export function WerkplekClient() {
  const [wetten, setWetten] = useState<WetChoice[]>([]);
  const [documenten, setDocumenten] = useState<DocumentSamenvatting[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [docs, setDocs] = useState<Record<string, AnnotatieDocument>>({});
  const [infos, setInfos] = useState<Record<string, GraafArtikel>>({});
  const [invoer, setInvoer] = useState("");
  const [bezig, setBezig] = useState(false);
  const [actiefId, setActiefId] = useState<string | undefined>();
  const [hoogte, setHoogte] = useState<string>("70dvh");
  const [menuOpen, setMenuOpen] = useState(false); // mobiele documenten-drawer
  const sessieRef = useRef<string>("");
  const lijstRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    sessieRef.current = sessie();
    listWetten().then(setWetten).catch(() => setWetten([]));
    verversLijst();
  }, []);

  // Vul de ruimte tussen de eigen bovenkant en de globale footer (runtime gemeten; geen magische
  // aftrek), zodat de invoerbalk laag staat en alleen de thread scrollt — én de footer + de onderrand
  // van <main> zichtbaar blijven i.p.v. onder de viewport te vallen. Herberekenen bij resize/toetsenbord
  // (visualViewport op mobiel); de footer wordt op smalle schermen hoger (tekst wrapt), dus meten.
  useLayoutEffect(() => {
    const meet = () => {
      const top = rootRef.current?.getBoundingClientRect().top ?? 0;
      const vh = window.visualViewport?.height ?? window.innerHeight;
      const footer = document.querySelector("footer");
      const footerH = footer ? footer.offsetHeight : 0;
      const mainEl = rootRef.current?.closest("main");
      const mainPb = mainEl ? parseFloat(getComputedStyle(mainEl).paddingBottom) || 0 : 0;
      // Reserveer de footer + de onderpadding van <main> + een kleine tussenruimte.
      const reserve = footerH + mainPb + 8;
      setHoogte(`${Math.max(320, Math.round(vh - top - reserve))}px`);
    };
    meet();
    window.addEventListener("resize", meet);
    window.visualViewport?.addEventListener("resize", meet);
    return () => {
      window.removeEventListener("resize", meet);
      window.visualViewport?.removeEventListener("resize", meet);
    };
  }, []);

  useEffect(() => {
    lijstRef.current?.scrollTo({ top: lijstRef.current.scrollHeight, behavior: "smooth" });
  }, [items, bezig]);

  // Escape sluit de mobiele drawer.
  useEffect(() => {
    if (!menuOpen) return;
    const opEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    window.addEventListener("keydown", opEsc);
    return () => window.removeEventListener("keydown", opEsc);
  }, [menuOpen]);

  // Auto-groeiende textarea (groeit met de inhoud tot een max; daarna intern scrollen).
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [invoer]);

  function verversLijst() {
    lijstDocumenten().then(setDocumenten).catch(() => {});
  }
  function updateItem(id: string, patch: Partial<Item>) {
    setItems((xs) => xs.map((x) => (x.id === id ? ({ ...x, ...patch } as Item) : x)));
  }

  async function verstuur(vast?: string) {
    const prompt = (vast ?? invoer).trim();
    if (!prompt || bezig) return;
    setInvoer("");
    const antId = uid();
    setItems((xs) => [...xs, { id: uid(), type: "user", tekst: prompt }, { id: antId, type: "antwoord", tekst: "" }]);
    setBezig(true);

    const doelRef: { d: AgentDoel | null } = { d: null };
    const els: VoorstelElement[] = [];
    const ontbrekend: OntbrekendItem[] = [];
    let tekst = "";
    let denk = "";
    try {
      await annoteerAgentStream(
        prompt,
        {
          // Het denkproces (statusstappen + tool-narratie) stroomt naar `denk`; het eindantwoord
          // naar `tekst`. De frontend toont ze gescheiden (inklapbaar denkproces-blok + antwoord).
          onStatus: (m) => {
            denk += (denk ? "\n" : "") + "· " + m;
            updateItem(antId, { denk });
          },
          onReason: (t) => {
            denk += t;
            updateItem(antId, { denk });
          },
          onToken: (t) => {
            tekst += t;
            updateItem(antId, { tekst });
          },
          onSources: (b) => updateItem(antId, { bronnen: b }),
          onDoel: (d) => (doelRef.d = d),
          onElement: (e) => els.push(e),
          onOntbrekend: (items) => ontbrekend.push(...items),
        },
        sessieRef.current,
      );

      const doel = doelRef.d;
      if (doel && doel.bwbId) {
        // De ophaal-agent stuurt de opgehaalde tekst mee in het doel — gebruik dát (één bron; werkt ook
        // voor beleidsregels/divisies zoals '9.1'). Val alleen terug op de graaf als het ontbreekt.
        const graaf: GraafArtikel = doel.leden_teksten?.length
          ? {
              bwbId: doel.bwbId,
              artikel: doel.artikel,
              citeertitel: doel.citeertitel ?? "",
              opschrift: "",
              leden_teksten: doel.leden_teksten,
            }
          : await haalArtikelGraaf(doel.bwbId, doel.artikel, doel.lid);
        const document = await maakDocument({ bwbId: doel.bwbId, artikel: doel.artikel, lid: doel.lid || null });
        const bijgewerkt = await zetElementen(document.slug, els);
        setDocs((m) => ({ ...m, [bijgewerkt.slug]: bijgewerkt }));
        setInfos((m) => ({ ...m, [bijgewerkt.slug]: graaf }));
        setItems((xs) =>
          xs.map((x) =>
            x.id === antId ? { id: antId, type: "annotatie", slug: bijgewerkt.slug, ontbrekend } : x,
          ),
        );
        verversLijst();
      } else if (!tekst.trim()) {
        updateItem(antId, { tekst: "(geen antwoord)" });
      }
    } catch (e) {
      updateItem(antId, { tekst: `⚠️ ${foutTekst(e)}` });
    } finally {
      setBezig(false);
    }
  }

  async function openDocument(slug: string) {
    if (!docs[slug]) {
      try {
        const document = await haalDocument(slug);
        const graaf = await haalArtikelGraaf(document.bwbId, document.artikel, document.lid);
        setDocs((m) => ({ ...m, [slug]: document }));
        setInfos((m) => ({ ...m, [slug]: graaf }));
      } catch (e) {
        setItems((xs) => [...xs, { id: uid(), type: "antwoord", tekst: `⚠️ ${foutTekst(e)}` }]);
        return;
      }
    }
    // Staat dit document al open in de thread? Dan geen tweede kaart toevoegen (voorkomt duplicaten
    // bij herhaald klikken in het linkermenu).
    setItems((xs) =>
      xs.some((x) => x.type === "annotatie" && x.slug === slug)
        ? xs
        : [...xs, { id: uid(), type: "annotatie", slug }],
    );
  }

  async function verwijder(slug: string) {
    if (!window.confirm("Dit annotatie-document verwijderen? Dit kan niet ongedaan worden gemaakt.")) return;
    try {
      await verwijderDocument(slug);
      setItems((xs) => xs.filter((x) => !(x.type === "annotatie" && x.slug === slug)));
      verversLijst();
    } catch {
      /* stil */
    }
  }

  async function beslissing(slug: string, elementId: string, req: BeslissingInvoer) {
    try {
      const bij = await beslis(slug, elementId, req);
      setDocs((m) => ({ ...m, [slug]: bij }));
      verversLijst();
    } catch (e) {
      // Niet stil slikken: een mislukte beslissing (409/422/404/429/netwerk) verdampt anders zonder
      // dat de jurist het merkt — de kaart sluit alsof het lukte. Toon de fout in de thread.
      setItems((xs) => [...xs, { id: uid(), type: "antwoord", tekst: `⚠️ Beslissing mislukt: ${foutTekst(e)}` }]);
    }
  }

  function opToets(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void verstuur();
    }
  }

  return (
    <div
      ref={rootRef}
      style={{ height: hoogte }}
      className="grid gap-4 lg:grid-cols-[minmax(220px,260px)_1fr]"
    >
      {/* Zijpaneel met lopende annotaties (desktop; op mobiel via de drawer hieronder) */}
      <div className="hidden min-h-0 overflow-y-auto lg:block">
        <DocumentLijst
          documenten={documenten}
          wetten={wetten}
          onOpen={openDocument}
          onNew={() => setItems([])}
          onVerwijder={verwijder}
        />
      </div>

      {/* Mobiele drawer met dezelfde documentenlijst */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Annotaties">
          <div className="absolute inset-0 bg-ink/40" onClick={() => setMenuOpen(false)} />
          <div className="absolute inset-y-0 left-0 w-[82%] max-w-xs overflow-y-auto bg-paper p-3 shadow-xl">
            <div className="mb-2 flex items-center justify-between">
              <span className="font-display text-sm font-semibold text-lint">Annotaties</span>
              <button
                type="button"
                onClick={() => setMenuOpen(false)}
                aria-label="Sluiten"
                className="rounded-lg px-2 py-1 text-muted transition-colors hover:text-ink"
              >
                ✕
              </button>
            </div>
            <DocumentLijst
              documenten={documenten}
              wetten={wetten}
              onOpen={(slug) => {
                setMenuOpen(false);
                void openDocument(slug);
              }}
              onNew={() => {
                setMenuOpen(false);
                setItems([]);
              }}
              onVerwijder={verwijder}
            />
          </div>
        </div>
      )}

      <div className="flex min-h-0 min-w-0 flex-col">
        {/* Mobiele triggerbalk voor de documenten-drawer (desktop heeft de zijkolom) */}
        <div className="mb-1 flex shrink-0 lg:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink transition-colors hover:border-lint"
            aria-label="Annotaties openen"
          >
            <span aria-hidden>☰</span>
            <span>Annotaties{documenten.length > 0 ? ` (${documenten.length})` : ""}</span>
          </button>
        </div>

        {/* Thread — enige scrollende gebied; berichten in een gecentreerde leeskolom */}
        <div ref={lijstRef} className="min-h-0 flex-1 overflow-y-auto" aria-live="polite">
          <div className="mx-auto max-w-3xl space-y-6 px-1 py-6">
            {items.length === 0 && (
              <div className="pt-6 text-center">
                <p className="font-display text-lg font-semibold text-lint">Waarmee kan ik helpen?</p>
                <p className="mt-1 text-sm text-muted">
                  Stel een vraag over de wet- en regelgeving, of vraag een annotatie volgens het JAS.
                </p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  {VOORBEELDEN.map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => void verstuur(v)}
                      className="rounded-full border border-line bg-paper px-3 py-1.5 text-left text-xs text-lint transition-colors hover:bg-surface"
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {items.map((item) =>
              item.type === "user" ? (
                <div key={item.id} className="flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-accent px-4 py-2.5 text-sm text-paper">
                    {item.tekst}
                  </div>
                </div>
              ) : item.type === "antwoord" ? (
                <div key={item.id} className="text-sm text-ink">
                  {item.denk && <DenkProces tekst={item.denk} actief={bezig && !item.tekst} />}
                  {item.tekst ? (
                    <Markdown tekst={item.tekst} />
                  ) : item.denk ? null : (
                    <Punten />
                  )}
                  {item.bronnen && item.bronnen.length > 0 && <Bronnen bronnen={item.bronnen} />}
                </div>
              ) : docs[item.slug] && infos[item.slug] ? (
                <AnnotatieKaart
                  key={item.id}
                  doc={docs[item.slug]}
                  info={infos[item.slug]}
                  ontbrekend={item.ontbrekend}
                  actiefId={actiefId}
                  onKies={setActiefId}
                  onBeslissing={(elementId, req) => beslissing(item.slug, elementId, req)}
                />
              ) : null,
            )}
          </div>
        </div>

        {/* Invoerbalk — gepind onderaan, gecentreerd, auto-groeiend */}
        <div className="shrink-0 bg-paper">
          <div className="mx-auto max-w-3xl px-1 pb-3 pt-2">
            <div className="flex items-end gap-2 rounded-2xl border border-line bg-white px-2 py-1.5 focus-within:border-lint">
              <textarea
                ref={taRef}
                value={invoer}
                onChange={(e) => setInvoer(e.target.value)}
                onKeyDown={opToets}
                rows={1}
                placeholder="Stel een vraag of vraag een annotatie…"
                className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-ink placeholder:text-faint focus:outline-none"
              />
              <Button onClick={() => verstuur()} disabled={bezig || !invoer.trim()} size="sm" className="mb-0.5 w-auto shrink-0">
                {bezig ? "…" : "Stuur"}
              </Button>
            </div>
            <p className="mt-2 text-center text-xs text-faint">
              De agent bevraagt de kennisgraaf — controleer altijd de bron.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

const VOORBEELDEN = [
  "Wat betekent het begrip 'belastingschuldige'?",
  "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
  "Welke artikelen gaan over invordering?",
];

function AnnotatieKaart({
  doc,
  info,
  ontbrekend,
  actiefId,
  onKies,
  onBeslissing,
}: {
  doc: AnnotatieDocument;
  info: GraafArtikel;
  ontbrekend?: OntbrekendItem[];
  actiefId?: string;
  onKies: (id?: string) => void;
  onBeslissing: (elementId: string, req: BeslissingInvoer) => Promise<void>;
}) {
  const opschrift = `${info.citeertitel || doc.bwbId} — artikel ${info.artikel}${doc.lid ? ` lid ${doc.lid}` : ""}`;
  return (
    <div className="grid gap-4 rounded-xl border border-line bg-surface p-3 lg:grid-cols-[1.4fr_1fr]">
      <DocumentPaneel
        opschrift={opschrift}
        leden={ledenVan(info)}
        elementen={doc.elementen.map((e) => ({ id: e.id, klasse: e.klasse, tekst: e.tekst }))}
        actiefId={actiefId}
        onKies={onKies}
      />
      <div className="space-y-3">
        {doc.elementen.length > 0 ? (
          <ReviewQueue elementen={doc.elementen} actiefId={actiefId} onKies={onKies} onBeslissing={onBeslissing} />
        ) : (
          <p className="text-sm text-muted">Geen elementen.</p>
        )}
        {ontbrekend && ontbrekend.length > 0 && (
          <div className="rounded-xl border border-dashed border-line bg-paper p-3">
            <p className="text-xs font-medium text-muted">Mogelijk ontbrekend (Critic-suggestie)</p>
            <ul className="mt-1.5 space-y-1">
              {ontbrekend.map((o, i) => (
                <li key={i} className="flex items-start gap-1.5 text-xs">
                  <span className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${jasStyle(o.klasse)}`}>{o.klasse}</span>
                  {o.reden && <span className="text-muted">{o.reden}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function Punten() {
  return (
    <span className="inline-flex gap-1" aria-label="Bezig">
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" />
    </span>
  );
}

// Inklapbaar "Denkproces"-blok (Claude-stijl): streamt live terwijl de agent werkt (`actief`) en klapt
// automatisch dicht zodra het antwoord er is. De gebruiker kan het handmatig weer openen.
function DenkProces({ tekst, actief }: { tekst: string; actief: boolean }) {
  // `open` volgt standaard `actief` (open tijdens streamen, dicht zodra het antwoord landt); zodra de
  // gebruiker zelf klikt, wint die keuze. Afgeleid tijdens render — geen setState-in-effect.
  const [keuze, setKeuze] = useState<boolean | null>(null);
  const open = keuze ?? actief;

  return (
    <div className="mb-2">
      <button
        type="button"
        onClick={() => setKeuze(!open)}
        className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink"
        aria-expanded={open}
      >
        {actief && (
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-muted" aria-hidden />
        )}
        <span>{actief ? "Denkt na…" : "Denkproces"}</span>
        <span className={`transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
          ▸
        </span>
      </button>
      {open && (
        <div className="mt-1.5 whitespace-pre-wrap border-l-2 border-line pl-3 text-xs leading-relaxed text-muted [overflow-wrap:anywhere]">
          {tekst}
        </div>
      )}
    </div>
  );
}

// Inklapbare bronnenlijst — standaard dicht met een teller, want de lijst kan lang zijn.
function Bronnen({ bronnen }: { bronnen: Bron[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-ink"
        aria-expanded={open}
      >
        <span className="font-medium">Bronnen ({bronnen.length})</span>
        <span className={`transition-transform ${open ? "rotate-90" : ""}`} aria-hidden>
          ▸
        </span>
      </button>
      {open && (
        <div className="mt-1.5 break-words border-l-2 border-line pl-3 text-xs text-muted [overflow-wrap:anywhere]">
          {bronnen.map((b, i) => {
            const href = wettenOverheidHref(b.uri);
            return (
              <span key={i}>
                {i > 0 && ", "}
                {href ? (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-lint underline underline-offset-2 [overflow-wrap:anywhere]"
                  >
                    {b.label}
                  </a>
                ) : (
                  b.label
                )}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
