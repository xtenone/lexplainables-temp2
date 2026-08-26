"""Opslag-agnostische traversal van het BWB-model naar een platte ``Batch``.

Loopt één keer door een :class:`~app.models.Wet` en verzamelt nodes, relaties en
verwijzingen in een neutrale representatie. De GraphDB-writer consumeert die
``Batch``, zodat de ref_key-/Citeerbaar-/verwijzing-logica (inclusief de telling
in :class:`~app.models.ImportSummary`) op één plek staat.

Elke node die JuriConnect-adresseerbaar is (wet, structuurdeel, artikel, lid,
onderdeel, divisie) draagt naast zijn XML-``id`` een ``ref_key``. Die sleutel is
de stabiele identiteit voor citaties: een ``VERWIJST_NAAR`` naar een nog niet
geïmporteerde wet gebruikt dezelfde ref_key, zodat de doel-node later
automatisch samenvalt (dezelfde IRI). Verwijzingen worden toegeschreven aan de
dichtstbijzijnde voorouder mét ref_key (onderdeel -> lid -> artikel).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models import (
    Artikel,
    Bijlage,
    Divisie,
    Illustratie,
    ImportSummary,
    Onderdeel,
    Ondertekenaar,
    Structuurdeel,
    Verwijzing,
    Wet,
)
from app.references import (
    detect_textual_references,
    jci_doel,
    jci_doel_ref_key,
    jci_to_ref_key,
)

# Relatie van ouder naar structuurdeel, per soort.
STRUCT_REL = {
    "hoofdstuk": "HEEFT_HOOFDSTUK",
    "titeldeel": "HEEFT_TITELDEEL",
    "afdeling": "HEEFT_AFDELING",
    "paragraaf": "HEEFT_PARAGRAAF",
}
# Structuursoort -> entiteitsnaam (voor label/klasse).
STRUCT_LABEL = {
    "hoofdstuk": "Hoofdstuk",
    "titeldeel": "Titeldeel",
    "afdeling": "Afdeling",
    "paragraaf": "Paragraaf",
}
# Structuursoort -> teller in ImportSummary.
_STRUCT_TELLER = {
    "hoofdstuk": "hoofdstukken",
    "titeldeel": "titeldelen",
    "afdeling": "afdelingen",
    "paragraaf": "paragrafen",
}

# Doel-soorten waarvan het "nummer" een artikelnummer is (voor labels).
_ARTIKEL_SOORTEN = {"artikel", "lid", "onderdeel"}


@dataclass
class Batch:
    """Verzamelde nodes en relaties, klaar om te schrijven.

    - ``nodes``: entiteit -> lijst prop-dicts (elk met ``id``; nodes met een
      JuriConnect-identiteit dragen ook ``ref_key``).
    - ``rels``: ``(src_ent, rel_type, dst_ent)`` -> rijen ``{"from": id, "to": id}``.
    - ``verwijzingen``: rijen met ``from``/``to`` als *ref_key* plus
      soort/doc/doel-metadata.
    """

    nodes: dict[str, list[dict]] = field(default_factory=dict)
    rels: dict[tuple[str, str, str], list[dict]] = field(default_factory=dict)
    verwijzingen: list[dict] = field(default_factory=list)

    def node(self, entiteit: str, props: dict) -> None:
        self.nodes.setdefault(entiteit, []).append(props)

    def rel(self, src: str, rel_type: str, dst: str, from_id: str, to_id: str) -> None:
        self.rels.setdefault((src, rel_type, dst), []).append({"from": from_id, "to": to_id})


class _Collector:
    """Bouwt een :class:`Batch` uit een :class:`Wet` (één traversal)."""

    def __init__(self, wet: Wet, *, tekstuele_refs: bool = True) -> None:
        self._bwb = wet.bwb_id
        self._tekstuele_refs = tekstuele_refs
        self.batch = Batch()
        self.summary = ImportSummary(bwb_id=wet.bwb_id, wetten=1)

    def run(self, wet: Wet) -> None:
        self.batch.node(
            "Regeling",
            {
                "id": wet.bwb_id,
                "bwb_id": wet.bwb_id,
                "ref_key": wet.bwb_id,
                "label_id": wet.label_id,
                "citeertitel": wet.citeertitel,
                "opschrift": wet.opschrift,
                "soort": wet.soort,
                "geldig_vanaf": wet.geldig_vanaf,
                "geldig_tot": wet.geldig_tot,
                "publicatiejaar": wet.publicatiejaar,
                "publicatienr": wet.publicatienr,
                "ondertekeningsdatum": wet.ondertekeningsdatum,
                "uitgiftedatum": wet.uitgiftedatum,
                "dossier": wet.dossier,
                "aanhef": wet.aanhef,
                "considerans": wet.considerans,
                "stub": False,
            },
        )
        for deel in wet.structuurdelen:
            self._structuur(deel, wet.bwb_id, "Regeling")
        self._artikelen(wet.losse_artikelen, wet.bwb_id, "Regeling")
        self._divisies(wet.divisies, wet.bwb_id, "Regeling")
        self._bijlagen(wet.bijlagen, wet.bwb_id, "Regeling")
        self._ondertekenaars(wet.ondertekenaars, wet.bwb_id)

    def _structuur(self, deel: Structuurdeel, ouder_id: str, ouder_ent: str) -> None:
        entiteit = STRUCT_LABEL[deel.soort]
        ref_key = jci_doel_ref_key(deel.jci)[0]
        if ref_key is None and deel.nummer:
            ref_key = f"{self._bwb}#{deel.soort}={deel.nummer}"
        self.batch.node(
            entiteit,
            {
                "id": deel.id,
                "nummer": deel.nummer,
                "label": deel.label,
                "titel": deel.titel,
                "soort": deel.soort,
                "ref_key": ref_key,
                "jci": deel.jci,
                "label_id": deel.label_id,
            },
        )
        self.batch.rel(ouder_ent, STRUCT_REL[deel.soort], entiteit, ouder_id, deel.id)
        teller = _STRUCT_TELLER[deel.soort]
        setattr(self.summary, teller, getattr(self.summary, teller) + 1)

        for sub in deel.subdelen:
            self._structuur(sub, deel.id, entiteit)
        self._artikelen(deel.artikelen, deel.id, entiteit)

    def _artikelen(self, artikelen: list[Artikel], ouder_id: str, ouder_ent: str) -> None:
        vorige_artikel: str | None = None
        for artikel in artikelen:
            ref_key = jci_to_ref_key(artikel.jci) or f"{self._bwb}#id={artikel.id}"
            self.batch.node(
                "Artikel",
                {
                    "id": artikel.id,
                    "nummer": artikel.nummer,
                    "label": artikel.label,
                    "tekst": artikel.tekst,
                    "ref_key": ref_key,
                    "jci": artikel.jci,
                    "label_id": artikel.label_id,
                    "inwerking": artikel.inwerking,
                    "bron": artikel.bron,
                    "effect": artikel.effect,
                    "status": artikel.status,
                    "terugwerkend_tot": artikel.terugwerkend_tot,
                    "wijzigingsbronnen": artikel.wijzigingsbronnen,
                    "voetnoot": artikel.voetnoten,
                },
            )
            self.batch.rel(ouder_ent, "HEEFT_ARTIKEL", "Artikel", ouder_id, artikel.id)
            self.summary.artikelen += 1
            if vorige_artikel is not None:
                self.batch.rel("Artikel", "VOLGT_OP", "Artikel", artikel.id, vorige_artikel)
            vorige_artikel = artikel.id

            self._verwijzingen(ref_key, artikel.verwijzingen, artikel.tekst)
            self._illustraties("Artikel", artikel.id, artikel.illustraties)
            self._leden(artikel, ref_key)
            self._onderdelen(artikel.onderdelen, artikel.id, "Artikel", ref_key)

    def _divisies(self, divisies: list[Divisie], ouder_id: str, ouder_ent: str) -> None:
        vorige_divisie: str | None = None
        for divisie in divisies:
            ref_key = jci_to_ref_key(divisie.jci) or f"{self._bwb}#id={divisie.id}"
            self.batch.node(
                "Divisie",
                {
                    "id": divisie.id,
                    "nummer": divisie.nummer,
                    "label": divisie.label,
                    "titel": divisie.titel,
                    "tekst": divisie.tekst,
                    "ref_key": ref_key,
                    "jci": divisie.jci,
                    "inwerking": divisie.inwerking,
                    "bron": divisie.bron,
                    "effect": divisie.effect,
                    "status": divisie.status,
                    "terugwerkend_tot": divisie.terugwerkend_tot,
                    "wijzigingsbronnen": divisie.wijzigingsbronnen,
                    "voetnoot": divisie.voetnoten,
                },
            )
            self.batch.rel(ouder_ent, "HEEFT_DIVISIE", "Divisie", ouder_id, divisie.id)
            self.summary.divisies += 1
            if vorige_divisie is not None:
                self.batch.rel("Divisie", "VOLGT_OP", "Divisie", divisie.id, vorige_divisie)
            vorige_divisie = divisie.id

            self._verwijzingen(ref_key, divisie.verwijzingen, divisie.tekst)
            self._illustraties("Divisie", divisie.id, divisie.illustraties)
            self._onderdelen(divisie.onderdelen, divisie.id, "Divisie", ref_key)
            self._divisies(divisie.subdivisies, divisie.id, "Divisie")

    def _bijlagen(self, bijlagen: list[Bijlage], ouder_id: str, ouder_ent: str) -> None:
        vorige_bijlage: str | None = None
        for bijlage in bijlagen:
            ref_key = jci_to_ref_key(bijlage.jci) or f"{self._bwb}#id={bijlage.id}"
            self.batch.node(
                "Bijlage",
                {
                    "id": bijlage.id,
                    "nummer": bijlage.nummer,
                    "label": bijlage.label,
                    "titel": bijlage.titel,
                    "tekst": bijlage.tekst,
                    "ref_key": ref_key,
                    "jci": bijlage.jci,
                    "inwerking": bijlage.inwerking,
                    "bron": bijlage.bron,
                    "effect": bijlage.effect,
                    "status": bijlage.status,
                    "terugwerkend_tot": bijlage.terugwerkend_tot,
                    "wijzigingsbronnen": bijlage.wijzigingsbronnen,
                    "voetnoot": bijlage.voetnoten,
                },
            )
            self.batch.rel(ouder_ent, "HEEFT_BIJLAGE", "Bijlage", ouder_id, bijlage.id)
            self.summary.bijlagen += 1
            if vorige_bijlage is not None:
                self.batch.rel("Bijlage", "VOLGT_OP", "Bijlage", bijlage.id, vorige_bijlage)
            vorige_bijlage = bijlage.id

            self._verwijzingen(ref_key, bijlage.verwijzingen, bijlage.tekst)
            self._illustraties("Bijlage", bijlage.id, bijlage.illustraties)
            self._onderdelen(bijlage.onderdelen, bijlage.id, "Bijlage", ref_key)
            # Een bijlage kan eigen artikelen bevatten (aparte Artikel-nodes).
            self._artikelen(bijlage.artikelen, bijlage.id, "Bijlage")

    def _illustraties(self, ouder_ent: str, ouder_id: str, illustraties: list[Illustratie]) -> None:
        for illustratie in illustraties:
            self.batch.node(
                "Illustratie",
                {
                    "id": illustratie.id,
                    "naam": illustratie.naam,
                    "formaat": illustratie.formaat,
                    "breedte": illustratie.breedte,
                    "hoogte": illustratie.hoogte,
                    "alt": illustratie.alt,
                },
            )
            self.batch.rel(ouder_ent, "BEVAT_ILLUSTRATIE", "Illustratie", ouder_id, illustratie.id)
            self.summary.illustraties += 1

    def _ondertekenaars(self, ondertekenaars: list[Ondertekenaar], bwb_id: str) -> None:
        """Ondertekenaar-nodes met een wet-overstijgende slug-IRI (dezelfde persoon
        valt over regelingen heen samen) en een ONDERTEKEND_DOOR-relatie."""
        for index, ondertekenaar in enumerate(ondertekenaars):
            sleutel = (
                " ".join(
                    deel
                    for deel in (
                        ondertekenaar.functie,
                        ondertekenaar.naam or ondertekenaar.achternaam,
                    )
                    if deel
                )
                or f"{bwb_id}-{index}"
            )
            node_id = f"{bwb_id}/ondertekenaar/{index}"
            self.batch.node(
                "Ondertekenaar",
                {
                    "id": node_id,
                    "iri_soort": "ondertekenaar",
                    "iri_sleutel": sleutel,
                    "functie": ondertekenaar.functie,
                    "naam": ondertekenaar.naam,
                    "voornaam": ondertekenaar.voornaam,
                    "achternaam": ondertekenaar.achternaam,
                    "plaats": ondertekenaar.plaats,
                    "ondertekeningsdatum": ondertekenaar.datum,
                },
            )
            self.batch.rel("Regeling", "ONDERTEKEND_DOOR", "Ondertekenaar", bwb_id, node_id)
            self.summary.ondertekenaars += 1

    def _leden(self, artikel: Artikel, artikel_ref_key: str) -> None:
        vorige_lid: str | None = None
        for lid in artikel.leden:
            lb, la, ll = jci_doel(lid.jci)
            lid_ref = f"{lb}#artikel={la}#lid={ll}" if lb and la and ll else None
            self.batch.node(
                "Lid",
                {
                    "id": lid.id,
                    "nummer": lid.nummer,
                    "tekst": lid.tekst,
                    "jci": lid.jci,
                    "ref_key": lid_ref,
                    "terugwerkend_tot": lid.terugwerkend_tot,
                    "voetnoot": lid.voetnoten,
                    "definieert_begrip": lid.definieert_begrippen,
                },
            )
            self.batch.rel("Artikel", "HEEFT_LID", "Lid", artikel.id, lid.id)
            self.summary.leden += 1
            if vorige_lid is not None:
                self.batch.rel("Lid", "VOLGT_OP", "Lid", lid.id, vorige_lid)
            vorige_lid = lid.id

            bron = lid_ref or artikel_ref_key
            self._verwijzingen(bron, lid.verwijzingen, lid.tekst)
            self._illustraties("Lid", lid.id, lid.illustraties)
            self._onderdelen(lid.onderdelen, lid.id, "Lid", bron)

    def _onderdelen(
        self,
        onderdelen: list[Onderdeel],
        ouder_id: str,
        ouder_ent: str,
        erf_ref_key: str,
    ) -> None:
        """``erf_ref_key`` is de ref_key van de dichtstbijzijnde voorouder;
        onderdelen zonder eigen jci schrijven hun verwijzingen daaraan toe."""
        for onderdeel in onderdelen:
            ref_key = jci_doel_ref_key(onderdeel.jci)[0]
            self.batch.node(
                "Onderdeel",
                {
                    "id": onderdeel.id,
                    "nummer": onderdeel.nummer,
                    "tekst": onderdeel.tekst,
                    "ref_key": ref_key,
                    "jci": onderdeel.jci,
                    "voetnoot": onderdeel.voetnoten,
                    "definieert_begrip": onderdeel.definieert_begrippen,
                },
            )
            self.batch.rel(ouder_ent, "HEEFT_ONDERDEEL", "Onderdeel", ouder_id, onderdeel.id)
            self.summary.onderdelen += 1

            bron = ref_key or erf_ref_key
            self._verwijzingen(bron, onderdeel.verwijzingen, onderdeel.tekst)
            self._illustraties("Onderdeel", onderdeel.id, onderdeel.illustraties)
            self._onderdelen(onderdeel.subonderdelen, onderdeel.id, "Onderdeel", bron)

    def _verwijzingen(self, ref_key: str, refs: list[Verwijzing], tekst: str | None) -> None:
        """Voeg de verwijzingen van één bron-node toe aan de batch.

        ``ref_key`` is de bronsleutel. Elk jci-doel wordt geresolveerd naar het
        meest specifieke niveau (wet/structuurdeel/artikel/lid/onderdeel); een
        verwijzing zonder jci valt terug op ``doel_pad``. Daarna detecteert de
        tekstuele fallback ongetagde verwijzingen in de lopende tekst
        (``soort=tekstueel``, ``betrouwbaarheid=laag``).
        """
        gezien: set[tuple[str, str]] = set()
        artikelnummers: set[str] = set()

        for verwijzing in refs:
            to_key, doel_soort = jci_doel_ref_key(verwijzing.doc)
            to_bwb, to_art, to_lid = jci_doel(verwijzing.doc)
            if to_key is None:
                # Zonder jci: val terug op het doel-pad (bwb-ng-variabel-deel);
                # dat mint dezelfde IRI als de doel-node zelf (by_id-schema).
                if not verwijzing.doel_pad:
                    continue
                to_bwb = verwijzing.doel_bwb_id or self._bwb
                to_key = f"{to_bwb}#id={to_bwb}{verwijzing.doel_pad}"
                doel_soort = "pad"
            if to_art:
                artikelnummers.add(to_art)
            if to_key == ref_key:
                continue  # zelfverwijzing
            sleutel = (to_key, verwijzing.soort.value)
            if sleutel in gezien:
                continue
            gezien.add(sleutel)
            self.batch.verwijzingen.append(
                {
                    "from": ref_key,
                    "to": to_key,
                    "to_bwb": to_bwb,
                    "to_nummer": _doel_nummer(to_key, doel_soort, to_art),
                    "doel_lid": to_lid,
                    "doel_soort": doel_soort,
                    "doel_pad": verwijzing.doel_pad,
                    "soort": verwijzing.soort.value,
                    "doc": verwijzing.doc,
                    "anker_tekst": verwijzing.tekst or None,
                    "verwijzing_id": verwijzing.verwijzing_id,
                }
            )

        if not (self._tekstuele_refs and tekst):
            return
        for verwijzing in detect_textual_references(tekst, eigen_bwb_id=self._bwb):
            # Ankertekst van een al gestructureerde verwijzing (zelfde
            # artikelnummer) opnieuw detecteren zou een dubbele/onterechte
            # edge opleveren -> overslaan.
            if verwijzing.doel_artikel in artikelnummers:
                continue
            to_key = f"{verwijzing.doel_bwb_id}#artikel={verwijzing.doel_artikel}"
            sleutel = (to_key, verwijzing.soort.value)
            if to_key == ref_key or sleutel in gezien:
                continue
            gezien.add(sleutel)
            self.batch.verwijzingen.append(
                {
                    "from": ref_key,
                    "to": to_key,
                    "to_bwb": verwijzing.doel_bwb_id,
                    "to_nummer": verwijzing.doel_artikel,
                    "doel_lid": None,
                    "doel_soort": "artikel",
                    "doel_pad": None,
                    "soort": verwijzing.soort.value,
                    "doc": None,
                    "anker_tekst": verwijzing.tekst,
                    "verwijzing_id": None,
                    "betrouwbaarheid": "laag",
                }
            )


def _doel_nummer(to_key: str, doel_soort: str | None, to_art: str | None) -> str | None:
    """Het "nummer" van het verwijsdoel: artikelnummer of structuurnummer."""
    if doel_soort in _ARTIKEL_SOORTEN:
        return to_art
    if doel_soort in STRUCT_LABEL:
        return to_key.rpartition("=")[2]
    return None


def collect(wet: Wet, *, tekstuele_refs: bool = True) -> tuple[Batch, ImportSummary]:
    """Loop de wet één keer door en geef de verzamelde ``Batch`` + telling terug."""
    collector = _Collector(wet, tekstuele_refs=tekstuele_refs)
    collector.run(wet)
    return collector.batch, collector.summary
