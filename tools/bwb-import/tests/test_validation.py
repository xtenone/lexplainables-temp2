"""Tests voor XSD-validatie (niet-blokkerend gedrag)."""

from __future__ import annotations

from pathlib import Path

from app.parser import ToestandParser


def test_geldige_xml_valideert(sample_xml: Path, toestand_xsd: Path) -> None:
    parser = ToestandParser(schema_path=toestand_xsd)
    assert parser.validate(sample_xml) is True


def test_zonder_schema_geen_validatie(sample_xml: Path) -> None:
    parser = ToestandParser(schema_path=None)
    assert parser.validate(sample_xml) is False


def test_ongeldige_xml_faalt_zacht(tmp_path: Path, toestand_xsd: Path) -> None:
    kapot = tmp_path / "kapot.xml"
    kapot.write_text("<toestand><onbekend/></toestand>", encoding="utf-8")
    parser = ToestandParser(schema_path=toestand_xsd)
    # Niet-blokkerend: geen exception, gewoon False.
    assert parser.validate(kapot) is False
