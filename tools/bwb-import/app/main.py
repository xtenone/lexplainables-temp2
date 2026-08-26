"""Orkestratie van de BWB-import: download -> validatie -> parse -> GraphDB.

Na ``python main.py`` wordt de toestand-XML gedownload, gevalideerd tegen het
XSD, geparsed en als RDF weggeschreven naar GraphDB, gevolgd door een overzicht
van het aantal geïmporteerde elementen en relaties.
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.config import Settings
from app.downloader import BwbDownloader
from app.graphdb_writer import GraphDbWriter
from app.models import ImportResult, ImportSummary, ToestandRef
from app.parser import ToestandParser
from app.rdf_vocab import Vocab
from app.wti_parser import WtiInfo, WtiParser

logger = logging.getLogger(__name__)


def maak_writer(settings: Settings) -> GraphDbWriter:
    return GraphDbWriter(
        url=settings.graphdb_url,
        repository=settings.graphdb_repository,
        vocab=Vocab(base=settings.graphdb_base_iri, ontology=settings.graphdb_ontology_iri),
        user=settings.graphdb_user,
        password=settings.graphdb_password,
        tekstuele_refs=settings.detect_tekstuele_refs,
    )


def prepare(writer: GraphDbWriter) -> None:
    """Eenmalige waarborgen per (batch-)import: repo, ontologie, FTS-index."""
    writer.ensure_constraints()
    writer.write_ontology()
    writer.ensure_fts_connector()


def run_import(
    bwb_id: str, settings: Settings, writer: GraphDbWriter | None = None
) -> ImportSummary:
    """Voer de volledige importpijplijn uit voor één regeling.

    Zonder meegegeven ``writer`` (losse aanroep) worden de waarborgen
    (:func:`prepare`) eerst uitgevoerd; in een batch gebeurt dat één keer.
    """
    logger.info("Start import voor %s (doel: GraphDB %s)", bwb_id, settings.graphdb_repository)

    if writer is None:
        writer = maak_writer(settings)
        prepare(writer)

    downloader = BwbDownloader(settings)
    toestand = downloader.latest_toestand(bwb_id)
    xml_path = downloader.download_toestand(bwb_id, toestand)

    schema_path = settings.schemas_dir / "toestand.xsd"
    parser = ToestandParser(schema_path=schema_path if settings.validate_xsd else None)
    if settings.validate_xsd:
        parser.validate(xml_path)

    wet = parser.parse(xml_path)
    # Geldigheidsvenster uit de SRU-index aanvullen.
    wet.geldig_vanaf = toestand.geldig_vanaf or wet.geldig_vanaf
    wet.geldig_tot = toestand.geldig_tot

    wti = _laad_wti(downloader, toestand) if settings.import_wti else None
    summary = writer.write_wet(wet, wti=wti)

    logger.info("Import voltooid voor %s", bwb_id)
    return summary


def _laad_wti(downloader: BwbDownloader, toestand: ToestandRef) -> WtiInfo | None:
    """Download en parse de WTI; verrijking is best-effort (nooit blokkerend)."""
    try:
        wti_path = downloader.download_wti(toestand)
        if wti_path is None:
            logger.warning("Geen WTI-locatie bekend voor %s", toestand.bwb_id)
            return None
        return WtiParser().parse(wti_path)
    except Exception as exc:  # noqa: BLE001 - verrijking mag de import niet breken
        logger.warning("WTI-verrijking overgeslagen voor %s: %s", toestand.bwb_id, exc)
        return None


def run_imports(bwb_ids: list[str], settings: Settings) -> list[ImportResult]:
    """Importeer meerdere regelingen sequentieel met één gedeelde writer.

    Per wet idempotent (named-graph PUT); een falende wet breekt de batch
    niet — de fout komt in het per-wet resultaat terecht.
    """
    writer = maak_writer(settings)
    prepare(writer)

    resultaten: list[ImportResult] = []
    for bwb_id in bwb_ids:
        try:
            summary = run_import(bwb_id, settings, writer=writer)
            resultaten.append(ImportResult(bwb_id=bwb_id, ok=True, overzicht=summary))
        except Exception as exc:  # noqa: BLE001 - batch loopt door, fout per wet
            logger.error("Import mislukt voor %s: %s", bwb_id, exc)
            resultaten.append(ImportResult(bwb_id=bwb_id, ok=False, fout=str(exc)))
    return resultaten


def _print_overzicht(summary: ImportSummary) -> None:
    regels = [
        ("Wet", summary.bwb_id),
        ("Wetten", summary.wetten),
        ("Hoofdstukken", summary.hoofdstukken),
        ("Afdelingen", summary.afdelingen),
        ("Paragrafen", summary.paragrafen),
        ("Divisies", summary.divisies),
        ("Artikelen", summary.artikelen),
        ("Leden", summary.leden),
        ("Onderdelen", summary.onderdelen),
        ("Relaties", summary.relaties),
    ]
    breedte = max(len(label) for label, _ in regels)
    print("\n=== Import-overzicht ===")
    for label, waarde in regels:
        print(f"  {label.ljust(breedte)} : {waarde}")
    print()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = Settings.from_env()

    parser = argparse.ArgumentParser(
        description="Importeer één of meer BWB-regelingen naar GraphDB."
    )
    parser.add_argument(
        "bwb_ids",
        nargs="*",
        default=[settings.default_bwb_id],
        help=f"BWB-id's van de regelingen (default: {settings.default_bwb_id})",
    )
    args = parser.parse_args(argv)
    bwb_ids = args.bwb_ids or [settings.default_bwb_id]

    resultaten = run_imports(bwb_ids, settings)
    for resultaat in resultaten:
        if resultaat.ok and resultaat.overzicht:
            _print_overzicht(resultaat.overzicht)
        else:
            logger.error("Import mislukt voor %s: %s", resultaat.bwb_id, resultaat.fout)

    return 0 if all(r.ok for r in resultaten) else 1


if __name__ == "__main__":
    sys.exit(main())
