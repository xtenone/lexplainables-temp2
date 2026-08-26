"""Export van één annotatiedocument: JSON, CSV of PDF.

Eén canonieke opbouw (`bouw_export`) en drie serialisaties. De opbouw is bewust de superset: hij
draagt het **volledige spoor** van elk element (alternatieven, Critic-rondes, anker, diff, alle
beslissingen, het model dat het voorstel maakte) plus het append-only auditlog. De JSON-variant is
letterlijk die structuur — daarmee is de export tegelijk het contract voor de latere promotie naar
de graaf (`docs/wetsanalyse-workbench/jas-annotatie-ontologie.md`).

Twee dingen zijn niet onderhandelbaar:

- **Brongetrouwheid.** De export toont de letterlijke wettekst per lid naast de tabel, zodat een
  markering altijd naast zijn bron te leggen is. Zijn de leden niet meegegeven, dan blijft dat blok
  weg — nooit een gereconstrueerde tekst.
- **Geen schijnzekerheid.** Een document dat nog in review is exporteert gewoon, maar draagt de
  status en de telling "te beoordelen" prominent in de kop. Een element zonder geregistreerd model
  toont `MODEL_ONBEKEND`, niet een lege cel: ontbrekende herkomst is een feit, geen vergissing.

De JAS-klassekleuren komen uit de canonieke skill-bron via `validation.py`, niet uit een tweede
lijstje hier.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from .annotatie_contracts import AgentRun, AnnotatieDocument, AnnotatieElement, AuditRecord
from .validation import JAS_KLASSE_KLEUREN, JAS_TEKSTKLEUR, jas_sorteersleutel

EXPORT_VERSIE = "1"
GENERATOR = "wetsanalyse-api"
MODEL_ONBEKEND = "onbekend (vóór registratie)"

# formaat -> (media_type, bestandsextensie)
FORMATEN: dict[str, tuple[str, str]] = {
    "json": ("application/json; charset=utf-8", "json"),
    "csv": ("text/csv; charset=utf-8", "csv"),
    "pdf": ("application/pdf", "pdf"),
}

# Mensleesbare status i.p.v. lifecycle-jargon — dezelfde woorden als de werkplek toont.
STATUS_LABEL = {
    "voorgesteld": "voorstel van Lex",
    "critic_checked": "voorstel van Lex (door Critic gezien)",
    "human_approved": "akkoord",
    "edited": "door jurist aangepast",
    "rejected": "verworpen",
    "published": "gepubliceerd",
    "reused": "hergebruikt",
}

# Achtergrondtinten voor de aandacht-as, gelijk aan frontend/app/globals.css.
AANDACHT_KLEUR = {"groen": "#e9f3e1", "geel": "#fbefe2", "rood": "#fbe7e5"}

NEUTRALE_KLEUR = ("#f5f6f8", "#d5d8dd")   # onbekende klasse — mag niet als JAS-kleur lezen


# --- exportmodel --------------------------------------------------------------

class LidTekst(BaseModel):
    """Eén lid letterlijke wettekst, zoals de werkplek hem toont (uit graph-qa)."""

    lid: str = ""
    tekst: str = ""


class ExportMeta(BaseModel):
    versie: str = EXPORT_VERSIE
    formaat: str = "json"
    gegenereerd_op: datetime
    generator: str = GENERATOR


class ExportTelling(BaseModel):
    totaal: int = 0
    beslist: int = 0
    te_beoordelen: int = 0
    van_agent: int = 0
    van_jurist: int = 0
    per_klasse: dict[str, int] = {}
    per_status: dict[str, int] = {}
    per_aandacht: dict[str, int] = {}


class ExportDocumentMeta(BaseModel):
    slug: str
    citeertitel: str = ""
    werkgebied: str = ""
    bwbId: str = ""
    artikel: str = ""
    lid: str = ""
    status: str = ""
    eigenaar: str = ""
    client_id: str = ""
    created: datetime | None = None
    updated: datetime | None = None
    runs: list[AgentRun] = []
    modellen: list[str] = []   # alle onderscheiden modellen die aan dit document werkten


class ExportElement(BaseModel):
    """Eén element met alles wat erover bekend is — niets weggelaten."""

    volgnummer: int
    id: str
    klasse: str
    kleur: str
    kleur_rand: str
    tekst: str
    lid: str = ""
    vindplaats: str = ""
    toelichting: str = ""
    herkomst: str = ""
    gewijzigd_door: str = ""
    lifecycle: str = ""
    status_label: str = ""
    aandacht: str = ""
    critic: str = ""
    alternatieven: list[dict] = []
    critic_rondes: list[dict] = []
    critic_suggestie: dict | None = None
    anker: dict | None = None
    diff: dict = {}
    beslissingen: list[dict] = []
    geproduceerd_door: AgentRun | None = None
    model: str = MODEL_ONBEKEND   # afgeleid, voor de tabelweergave


class ExportDocument(BaseModel):
    export: ExportMeta
    document: ExportDocumentMeta
    telling: ExportTelling = Field(default_factory=ExportTelling)
    leden: list[LidTekst] = []
    elementen: list[ExportElement] = []
    audit: list[AuditRecord] = []


# --- opbouw -------------------------------------------------------------------

def _lidsleutel(lid: str) -> tuple[int, str]:
    """Numeriek sorteren op lid: '10' hoort ná '2', en '2a' direct ná '2'."""
    m = re.match(r"\s*(\d+)\s*(.*)", lid or "")
    return (int(m.group(1)), m.group(2)) if m else (10**6, lid or "")


def _positie(el: AnnotatieElement) -> int:
    """Plek in de brontekst, als het anker die kent; anders achteraan binnen zijn groep."""
    return el.anker.start if el.anker else 10**9


def sorteer_elementen(elementen: list[AnnotatieElement]) -> list[AnnotatieElement]:
    """Canonieke JAS-tabelvolgorde → lid (numeriek) → plek in de tekst → invoervolgorde.

    Exact dezelfde sleutels als `sorteerReview` in de werkplek (frontend/lib/annotatie.ts), zodat
    de export in dezelfde volgorde staat als het scherm waarop de jurist hem beoordeelde.
    """
    return [
        el for _, el in sorted(
            enumerate(elementen),
            key=lambda p: (jas_sorteersleutel(p[1].klasse), _lidsleutel(p[1].lid), _positie(p[1]), p[0]),
        )
    ]


def _model_van(el: AnnotatieElement) -> str:
    if el.herkomst == "mens":
        return "n.v.t. (markering van de jurist)"
    if el.geproduceerd_door and el.geproduceerd_door.model:
        return el.geproduceerd_door.model
    return MODEL_ONBEKEND


def tel_elementen(elementen: list[AnnotatieElement]) -> ExportTelling:
    """De stand van zaken van één document: hoeveel beoordeeld, hoeveel aandacht, welke klassen.

    Eén waarheid over "hoeveel is er nog te beoordelen": zowel de export als de overzichtslijst
    (`GET /v1/annotatie/documenten`) rekenen hiermee. Twee tellingen naast elkaar spreken elkaar
    vroeg of laat tegen, en juist die telling stuurt de werkvoorraad van de jurist.
    """
    telling = ExportTelling(totaal=len(elementen))
    for el in elementen:
        lifecycle = el.lifecycle.value if el.lifecycle else ""
        aandacht = el.aandacht.value if el.aandacht else ""
        telling.per_klasse[el.klasse] = telling.per_klasse.get(el.klasse, 0) + 1
        sleutel = STATUS_LABEL.get(lifecycle, lifecycle or "onbekend")
        telling.per_status[sleutel] = telling.per_status.get(sleutel, 0) + 1
        telling.per_aandacht[aandacht or "geen"] = telling.per_aandacht.get(aandacht or "geen", 0) + 1
        if el.herkomst == "mens":
            telling.van_jurist += 1
        else:
            telling.van_agent += 1
        if el.beslissingen:
            telling.beslist += 1
        else:
            telling.te_beoordelen += 1
    return telling


def bouw_export(
    doc: AnnotatieDocument,
    audit: list[AuditRecord],
    leden: list[LidTekst] | None = None,
    formaat: str = "json",
) -> ExportDocument:
    elementen: list[ExportElement] = []
    telling = tel_elementen(doc.elementen)

    for i, el in enumerate(sorteer_elementen(doc.elementen), start=1):
        bg, rand = JAS_KLASSE_KLEUREN.get(el.klasse, NEUTRALE_KLEUR)
        lifecycle = el.lifecycle.value if el.lifecycle else ""
        aandacht = el.aandacht.value if el.aandacht else ""
        elementen.append(ExportElement(
            volgnummer=i, id=el.id, klasse=el.klasse, kleur=bg, kleur_rand=rand,
            tekst=el.tekst, lid=el.lid, vindplaats=el.vindplaats, toelichting=el.toelichting,
            herkomst=el.herkomst, gewijzigd_door=el.gewijzigd_door,
            lifecycle=lifecycle, status_label=STATUS_LABEL.get(lifecycle, lifecycle),
            aandacht=aandacht, critic=el.critic,
            alternatieven=[a.model_dump(mode="json") for a in el.alternatieven],
            critic_rondes=[r.model_dump(mode="json") for r in el.critic_rondes],
            critic_suggestie=el.critic_suggestie.model_dump(mode="json") if el.critic_suggestie else None,
            anker=el.anker.model_dump(mode="json") if el.anker else None,
            diff=el.diff,
            beslissingen=[b.model_dump(mode="json") for b in el.beslissingen],
            geproduceerd_door=el.geproduceerd_door,
            model=_model_van(el),
        ))

    modellen = list(dict.fromkeys(r.model for r in doc.runs if r.model))

    return ExportDocument(
        export=ExportMeta(formaat=formaat, gegenereerd_op=datetime.now(timezone.utc)),
        document=ExportDocumentMeta(
            slug=doc.slug, citeertitel=weergavenaam(doc), werkgebied=doc.werkgebied,
            bwbId=doc.bwbId, artikel=doc.artikel,
            lid=doc.lid, status=doc.status.value, eigenaar=doc.user_id, client_id=doc.client_id,
            created=doc.created, updated=doc.updated, runs=list(doc.runs), modellen=modellen,
        ),
        telling=telling,
        leden=list(leden or []),
        elementen=elementen,
        audit=list(audit),
    )


def weergavenaam(doc: AnnotatieDocument) -> str:
    """De naam waaronder een annotatie in beeld komt.

    Terugval op `werkgebied`: vóór het aparte `citeertitel`-veld zette de werkplek de wetnaam daarin
    (`werkgebied: doel.citeertitel`). Oude documenten zijn zo leesbaar zonder datamigratie — en
    zonder te gokken wat er in dat veld stond.
    """
    return doc.citeertitel or doc.werkgebied or doc.bwbId


def bestandsnaam(doc: AnnotatieDocument, formaat: str) -> str:
    ext = FORMATEN[formaat][1]
    deel = f"annotatie-{doc.bwbId or 'onbekend'}-art{doc.artikel or '0'}"
    if doc.lid:
        deel += f"-lid{doc.lid}"
    veilig = re.sub(r"[^A-Za-z0-9._-]", "-", f"{deel}-{doc.slug}")
    return f"{veilig}.{ext}"


# --- serialisaties ------------------------------------------------------------

def naar_json(e: ExportDocument) -> bytes:
    return e.model_dump_json(indent=2).encode("utf-8")


def _plat(waarde) -> str:
    """Meerdere regels in één CSV-cel; leesbaar in Excel en eenduidig te splitsen."""
    return " ⏎ ".join(str(w) for w in waarde if str(w).strip())


def _beslissingen_plat(el: ExportElement) -> str:
    return _plat([
        f"{b.get('type', '')}|{b.get('actor', '')}|{b.get('tijd', '')}"
        f"|{b.get('review_reason') or ''}|{b.get('comment', '')}"
        for b in el.beslissingen
    ])


CSV_KOLOMMEN = [
    "nr", "jas_klasse", "kleur_hex", "fragment", "lid", "vindplaats", "toelichting",
    "aandacht", "critic_motivatie", "status", "herkomst", "gewijzigd_door", "lifecycle",
    "alternatieven", "critic_rondes", "critic_suggestie", "anker", "diff", "beslissingen",
    "model", "provider", "agent_versie", "element_id",
]


def naar_csv(e: ExportDocument) -> bytes:
    """CSV met een metadata-blok bovenaan, zodat één bestand alles draagt.

    Excel-vriendelijk: `;` als scheidingsteken (NL-default) en een UTF-8 BOM, anders verminkt Excel
    de diacritieken. Kleur bestaat niet in CSV, dus de hexwaarde staat als kolom.
    """
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)

    d, t = e.document, e.telling
    for sleutel, waarde in [
        ("export_versie", e.export.versie), ("gegenereerd_op", e.export.gegenereerd_op.isoformat()),
        ("generator", e.export.generator), ("slug", d.slug), ("werkgebied", d.werkgebied),
        ("bwbId", d.bwbId), ("artikel", d.artikel), ("lid", d.lid), ("status", d.status),
        ("eigenaar", d.eigenaar), ("client_id", d.client_id),
        ("aangemaakt", d.created.isoformat() if d.created else ""),
        ("bijgewerkt", d.updated.isoformat() if d.updated else ""),
        ("modellen", ", ".join(d.modellen) or MODEL_ONBEKEND),
        ("agent_rondes", len(d.runs)),
        ("elementen_totaal", t.totaal), ("beslist", t.beslist), ("te_beoordelen", t.te_beoordelen),
        ("van_agent", t.van_agent), ("van_jurist", t.van_jurist),
    ]:
        w.writerow([f"# {sleutel}", waarde])
    w.writerow([])

    w.writerow(CSV_KOLOMMEN)
    for el in e.elementen:
        run = el.geproduceerd_door
        w.writerow([
            el.volgnummer, el.klasse, el.kleur, el.tekst, el.lid, el.vindplaats, el.toelichting,
            el.aandacht, el.critic, el.status_label, el.herkomst, el.gewijzigd_door, el.lifecycle,
            _plat(f"{a.get('klasse', '')}: {a.get('motivatie', '')}" for a in el.alternatieven),
            _plat(f"ronde {r.get('ronde', '')}|{r.get('aandacht') or ''}|{r.get('actie', '')}"
                  f"|{r.get('motivatie', '')}" for r in el.critic_rondes),
            "" if not el.critic_suggestie else
            f"{el.critic_suggestie.get('aandacht') or ''}|{el.critic_suggestie.get('status', '')}"
            f"|{el.critic_suggestie.get('motivatie', '')}",
            "" if not el.anker else
            f"lid {el.anker.get('lid', '')} [{el.anker.get('start')}–{el.anker.get('eind')}] "
            f"hash {el.anker.get('bron_hash', '')}",
            _plat(f"{veld}: '{w_.get('voor', '')}' → '{w_.get('na', '')}'" for veld, w_ in el.diff.items()),
            _beslissingen_plat(el),
            el.model, run.provider if run else "", run.agent_versie if run else "", el.id,
        ])

    # BOM zodat Excel het als UTF-8 opent.
    return "﻿".encode("utf-8") + buf.getvalue().encode("utf-8")


def naar_pdf(e: ExportDocument) -> bytes:
    """Het rapport in de vormtaal van de officiële JAS-tabel (docs/wetsanalyse/wa-table.png).

    reportlab wordt lazy geïmporteerd: alleen dit formaat heeft hem nodig, en zo blijft de
    app-start ongemoeid.
    """
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )

    ss = getSampleStyleSheet()
    st_titel = ParagraphStyle("wa-titel", parent=ss["Title"], fontSize=16, spaceAfter=2 * mm,
                              alignment=TA_LEFT, textColor=colors.HexColor("#154273"))
    st_kop = ParagraphStyle("wa-kop", parent=ss["Heading2"], fontSize=11.5, spaceBefore=5 * mm,
                            spaceAfter=2 * mm, textColor=colors.HexColor("#154273"))
    st_kop3 = ParagraphStyle("wa-kop3", parent=ss["Heading3"], fontSize=9.5, spaceBefore=3 * mm,
                             spaceAfter=1 * mm, textColor=colors.HexColor("#1A1A1A"))
    st = ParagraphStyle("wa", parent=ss["BodyText"], fontSize=8, leading=10.5)
    st_klein = ParagraphStyle("wa-klein", parent=st, fontSize=7, leading=9,
                              textColor=colors.HexColor("#4a4a4a"))
    st_cel = ParagraphStyle("wa-cel", parent=st, fontSize=7.5, leading=9.5)
    st_wet = ParagraphStyle("wa-wet", parent=st, fontSize=8.5, leading=12,
                            leftIndent=4 * mm, spaceAfter=1.5 * mm)

    def esc(tekst) -> str:
        """Wettekst en modeluitvoer mogen `<` en `&` bevatten; reportlab leest een alinea als
        mini-markup. Zonder deze escape breekt één citaat met een `<` het hele document."""
        return (str(tekst if tekst is not None else "")
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    def p(tekst, stijl=st_cel) -> Paragraph:
        """Inhoud: alles wordt geëscaped, niets wordt als opmaak gelezen."""
        return Paragraph(esc(tekst).replace("\n", "<br/>"), stijl)

    def pm(html: str, stijl=st_cel) -> Paragraph:
        """Een regel die ik zelf samenstel en waarin opmaak (`<b>`) bedoeld is. Elke ingevoegde
        waarde moet dan al door `esc()` zijn gegaan — vandaar de scheiding met `p()`."""
        return Paragraph(html, stijl)

    def tijdstip(waarde) -> str:
        """ISO-tijden uit de JSON-dumps leesbaar maken; onbekend formaat blijft ongewijzigd."""
        if isinstance(waarde, datetime):
            return f"{waarde:%d-%m-%Y %H:%M}"
        try:
            return f"{datetime.fromisoformat(str(waarde)):%d-%m-%Y %H:%M}"
        except ValueError:
            return str(waarde or "")

    d, t = e.document, e.telling
    bron = f"{d.citeertitel or d.bwbId} art. {d.artikel}" + (f" lid {d.lid}" if d.lid else "")
    verhaal: list = []

    # 1. Titelblok
    verhaal.append(p(f"JAS-annotatie — {bron}", st_titel))
    kop = [esc(d.werkgebied) or "geen werkgebied", f"status: {esc(d.status)}"]
    if t.te_beoordelen:
        kop.append(f"<b>{t.te_beoordelen} van {t.totaal} elementen nog te beoordelen</b>")
    else:
        kop.append(f"alle {t.totaal} elementen beoordeeld")
    verhaal.append(pm(" · ".join(kop), st))
    verhaal.append(p(
        "Dit rapport bevat voorstellen van een AI-agent die door een jurist zijn beoordeeld. "
        f"Gegenereerd op {e.export.gegenereerd_op:%d-%m-%Y %H:%M} UTC.", st_klein))

    # 2. Metadata — inclusief het model, want dat is de herkomst van elk voorstel.
    verhaal.append(p("Gegevens van de annotatie", st_kop))
    meta: list[tuple[str, str]] = [
        ("Regeling (bwbId)", d.bwbId), ("Artikel", d.artikel), ("Lid", d.lid or "hele artikel"),
        ("Werkgebied", d.werkgebied or "—"), ("Status", d.status),
        ("Documentsleutel", d.slug), ("Eigenaar", d.eigenaar or "—"),
        ("Herkomst (client)", d.client_id or "—"),
        ("Aangemaakt", f"{d.created:%d-%m-%Y %H:%M}" if d.created else "—"),
        ("Laatst bijgewerkt", f"{d.updated:%d-%m-%Y %H:%M}" if d.updated else "—"),
        ("Model(len)", ", ".join(d.modellen) or MODEL_ONBEKEND),
        ("Agent-rondes", str(len(d.runs))),
        ("Elementen", f"{t.totaal} (agent {t.van_agent}, jurist {t.van_jurist})"),
        ("Beoordeeld", f"{t.beslist} beslist, {t.te_beoordelen} te beoordelen"),
        ("Per aandacht", ", ".join(f"{k}: {v}" for k, v in t.per_aandacht.items()) or "—"),
        ("Per status", ", ".join(f"{k}: {v}" for k, v in t.per_status.items()) or "—"),
    ]
    for r in d.runs:
        meta.append((
            f"Ronde {r.ronde}",
            f"{r.model or MODEL_ONBEKEND} · {r.provider or '—'} · agent {r.agent_versie or '—'} · "
            f"{r.critic_rondes} critic-ronde(s) · {r.stop_reden or '—'} · "
            f"{r.tijd:%d-%m-%Y %H:%M}",
        ))
    tab_meta = Table([[p(k, st_cel), p(v, st_cel)] for k, v in meta],
                     colWidths=[45 * mm, 205 * mm], hAlign="LEFT")
    tab_meta.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5d8dd")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f5f6f8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    verhaal.append(tab_meta)

    # 3. De letterlijke wettekst — brongetrouwheid: de tabel moet naast zijn bron te leggen zijn.
    if e.leden:
        verhaal.append(p("Wettekst (letterlijk)", st_kop))
        for lid in e.leden:
            label = f"<b>Lid {esc(lid.lid)}.</b> " if lid.lid else ""
            verhaal.append(pm(label + esc(lid.tekst), st_wet))

    # 4. De hoofdtabel, in de kleuren van de JAS-tabel.
    verhaal.append(p("Markeringen", st_kop))
    kolomkop = ["#", "JAS-klasse", "Fragment (letterlijk)", "Lid", "Vindplaats", "Toelichting",
                "Aandacht", "Status", "Model"]
    rijen = [[p(k, st_cel) for k in kolomkop]]
    stijl: list = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#b8baba")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#154273")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for i, el in enumerate(e.elementen, start=1):
        rijen.append([
            p(el.volgnummer, st_cel), p(el.klasse, st_cel), p(el.tekst, st_cel), p(el.lid, st_cel),
            p(el.vindplaats, st_cel), p(el.toelichting, st_cel), p(el.aandacht or "—", st_cel),
            p(el.status_label, st_cel), p(el.model, st_cel),
        ])
        # Zo leest de tabel als wa-table.png: de klassecel draagt de labelkleur, niet de hele rij.
        stijl.append(("BACKGROUND", (1, i), (1, i), colors.HexColor(el.kleur)))
        stijl.append(("BOX", (1, i), (1, i), 0.6, colors.HexColor(el.kleur_rand)))
        stijl.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor(JAS_TEKSTKLEUR)))
        if el.aandacht in AANDACHT_KLEUR:
            stijl.append(("BACKGROUND", (6, i), (6, i), colors.HexColor(AANDACHT_KLEUR[el.aandacht])))
    if len(rijen) == 1:
        rijen.append([p("Nog geen markeringen in dit document.", st_cel)] + [p("", st_cel)] * 8)
    tab = Table(rijen, repeatRows=1, hAlign="LEFT",
                colWidths=[8 * mm, 32 * mm, 62 * mm, 10 * mm, 33 * mm, 55 * mm, 16 * mm, 20 * mm, 26 * mm])
    tab.setStyle(TableStyle(stijl))
    verhaal.append(tab)

    # 5. Bijlage A — het volledige spoor per element.
    verhaal.append(PageBreak())
    verhaal.append(p("Bijlage A — volledig spoor per markering", st_kop))
    if not e.elementen:
        verhaal.append(p("Geen markeringen.", st))
    for el in e.elementen:
        blok: list = [p(f"{el.volgnummer}. {el.klasse} — “{el.tekst}”", st_kop3)]
        regels = [
            f"<b>Vindplaats:</b> {esc(el.vindplaats) or '—'}"
            + (f" (lid {esc(el.lid)})" if el.lid else ""),
            f"<b>Toelichting:</b> {esc(el.toelichting) or '—'}",
            f"<b>Herkomst:</b> aangemaakt door {esc(el.herkomst)}"
            + (f", laatst gewijzigd door {esc(el.gewijzigd_door)}" if el.gewijzigd_door else "")
            + f" · status {esc(el.status_label)} · model {esc(el.model)}",
        ]
        if el.geproduceerd_door:
            r = el.geproduceerd_door
            regels.append(
                f"<b>Productie:</b> ronde {r.ronde} · {esc(r.provider) or '—'} · "
                f"agent {esc(r.agent_versie) or '—'} · {tijdstip(r.tijd)}")
        if el.aandacht or el.critic:
            regels.append(
                f"<b>Aandacht:</b> {esc(el.aandacht) or '—'} — {esc(el.critic) or 'geen motivatie'}")
        for a in el.alternatieven:
            regels.append(
                f"<b>Alternatief:</b> {esc(a.get('klasse'))} — {esc(a.get('motivatie'))}")
        for r_ in el.critic_rondes:
            regels.append(
                f"<b>Critic ronde {esc(r_.get('ronde'))}:</b> {esc(r_.get('aandacht')) or '—'} · "
                f"{esc(r_.get('actie'))} — {esc(r_.get('motivatie'))}")
        if el.critic_suggestie:
            cs = el.critic_suggestie
            regels.append(
                f"<b>Kanttekening bij eigen markering:</b> {esc(cs.get('aandacht')) or '—'} "
                f"({esc(cs.get('status'))}) — {esc(cs.get('motivatie'))}")
        for veld, wz in (el.diff or {}).items():
            regels.append(
                f"<b>Wijziging {esc(veld)}:</b> “{esc(wz.get('voor'))}” → “{esc(wz.get('na'))}”")
        for b in el.beslissingen:
            regels.append(
                f"<b>Beslissing {esc(b.get('type'))}:</b> {esc(b.get('actor')) or 'onbekend'} · "
                f"{tijdstip(b.get('tijd'))}"
                + (f" · reden {esc(b.get('review_reason'))}" if b.get("review_reason") else "")
                + (f" · “{esc(b.get('comment'))}”" if b.get("comment") else ""))
        if el.anker:
            a = el.anker
            regels.append(
                f"<b>Anker:</b> lid {esc(a.get('lid'))} tekens {a.get('start')}–{a.get('eind')} · "
                f"bron-hash {esc(a.get('bron_hash')) or '—'}")
        regels.append(f"<b>Element-id:</b> {esc(el.id)}")
        blok += [pm(r, st_klein) for r in regels]
        blok.append(Spacer(1, 2 * mm))
        verhaal.append(KeepTogether(blok))

    # 6. Bijlage B — het append-only auditlog als tijdlijn.
    verhaal.append(PageBreak())
    verhaal.append(p("Bijlage B — auditlog", st_kop))
    if not e.audit:
        verhaal.append(p("Geen auditregels.", st))
    else:
        audit_rijen = [[p(k, st_cel) for k in ("#", "Tijdstip", "Actor", "Actie", "Element", "Detail")]]
        for a in e.audit:
            audit_rijen.append([
                p(a.id, st_cel), p(f"{a.tijdstip:%d-%m-%Y %H:%M:%S}" if a.tijdstip else "—", st_cel),
                p(a.actor or "—", st_cel), p(a.actie, st_cel), p(a.element_id or "—", st_cel),
                p("; ".join(f"{k}={v}" for k, v in (a.detail or {}).items()), st_cel),
            ])
        tab_audit = Table(audit_rijen, repeatRows=1, hAlign="LEFT",
                          colWidths=[10 * mm, 27 * mm, 22 * mm, 34 * mm, 22 * mm, 147 * mm])
        tab_audit.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d5d8dd")),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#154273")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        verhaal.append(tab_audit)

    def voet(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#4a4a4a"))
        canvas.drawString(15 * mm, 10 * mm, f"{bron} · {e.export.generator} · AI-voorstel, beoordeeld door een jurist")
        canvas.drawRightString(landscape(A4)[0] - 15 * mm, 10 * mm, f"pagina {canvas.getPageNumber()}")
        canvas.restoreState()

    uit = io.BytesIO()
    sjabloon = SimpleDocTemplate(
        uit, pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm, bottomMargin=15 * mm,
        title=f"JAS-annotatie {bron}", author=GENERATOR, subject=d.werkgebied or "Wetsanalyse",
    )
    sjabloon.build(verhaal, onFirstPage=voet, onLaterPages=voet)
    return uit.getvalue()


SERIALISATIES = {"json": naar_json, "csv": naar_csv, "pdf": naar_pdf}


def serialiseer(e: ExportDocument, formaat: str) -> bytes:
    return SERIALISATIES[formaat](e)
