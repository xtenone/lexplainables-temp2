"""Gedeelde pytest-fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def sample_xml() -> Path:
    """Pad naar een valide, ingekorte toestand-XML (Invorderingswet 1990)."""
    return FIXTURES / "sample_toestand.xml"


@pytest.fixture
def sample_circulaire_xml() -> Path:
    """Pad naar een kleine circulaire-toestand (divisie-structuur)."""
    return FIXTURES / "sample_circulaire.xml"


@pytest.fixture
def sample_regeling_xml() -> Path:
    """Pad naar een kleine ministeriële regeling (<regeling>/<regeling-tekst>)."""
    return FIXTURES / "sample_regeling.xml"


@pytest.fixture
def sample_tabel_xml() -> Path:
    """Pad naar een minimale toestand met een CALS-tabel en een voetnoot."""
    return FIXTURES / "sample_tabel.xml"


@pytest.fixture
def sample_bijlage_xml() -> Path:
    """Pad naar een kleine toestand met een bijlage (illustratie + eigen artikel)."""
    return FIXTURES / "sample_bijlage.xml"


@pytest.fixture
def toestand_xsd() -> Path:
    """Pad naar het officiële toestand-XSD met lokale afhankelijkheden."""
    return PROJECT_ROOT / "schemas" / "toestand.xsd"
