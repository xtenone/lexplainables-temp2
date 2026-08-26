"""Drift-guard: de IRI-ruimte van de graaf, over de componentgrenzen heen.

Waarom deze test bestaat. De basis-IRI wordt geschreven door de importer en
gelezen door graph-qa en de frontend. Die drie leven in verschillende talen en
processen, dus er is geen compiler die ze aan elkaar houdt — en het faalgedrag is
stil: loopt graph-qa's filterwaarde uit de pas met wat de importer wegschrijft,
dan matcht `STRSTARTS` niets en krijgt de jurist een leeg antwoord in plaats van
een foutmelding. Precies dat kon gebeuren: de string stond op vijf plekken los.

Zelfde idioom als `test_contract_drift.py`: de andere componenten worden als
**bestand** gelezen, niet geïmporteerd, want hun venv is hier niet beschikbaar.
We vergelijken de defaults in de broncode — niet de runtime-waarde, want die
hangt van de omgeving af en zou de test van de machine afhankelijk maken.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

WORTEL = Path(__file__).resolve().parents[3]
RDF_VOCAB = WORTEL / "tools" / "bwb-import" / "app" / "rdf_vocab.py"
NAMESPACE = WORTEL / "tools" / "graph-qa" / "agent" / "namespace.py"
URL_TS = WORTEL / "frontend" / "lib" / "url.ts"


def _literal(pad: Path, patroon: str) -> str:
    tekst = pad.read_text(encoding="utf-8")
    treffer = re.search(patroon, tekst)
    assert treffer, f"{pad.name}: patroon niet gevonden — is de constante hernoemd? ({patroon})"
    return treffer.group(1)


@pytest.mark.parametrize(
    "naam, patroon_importer, patroon_agent",
    [
        ("basis", r'DEFAULT_BASE_IRI\s*=\s*"([^"]+)"', r'BASIS\s*=\s*os\.getenv\([^)]*\)\s*or\s*"([^"]+)"'),
        ("ontologie", r'DEFAULT_ONTOLOGY_IRI\s*=\s*"([^"]+)"', r'ONTOLOGIE\s*=\s*os\.getenv\([^)]*\)\s*or\s*"([^"]+)"'),
    ],
)
def test_agent_volgt_de_importer(naam: str, patroon_importer: str, patroon_agent: str) -> None:
    importer = _literal(RDF_VOCAB, patroon_importer)
    agent = _literal(NAMESPACE, patroon_agent)
    assert agent == importer, (
        f"{naam}-IRI loopt uiteen: de importer schrijft {importer!r}, graph-qa zoekt {agent!r}. "
        "Dat levert geen fout op maar een leeg antwoord — pas beide aan, of geef graph-qa "
        "GRAPHDB_BASE_IRI/GRAPHDB_ONTOLOGY_IRI mee."
    )


def test_frontend_volgt_de_importer() -> None:
    """De frontend vertaalt graaf-IRI's naar een publieke vindplaats en moet dus
    dezelfde basis kennen. Hij kan de env niet lezen (client-side), dus hier is de
    constante de enige koppeling — en daarmee de meest waarschijnlijke drift."""
    importer = _literal(RDF_VOCAB, r'DEFAULT_BASE_IRI\s*=\s*"([^"]+)"')
    frontend = _literal(URL_TS, r'GRAAF_BASIS\s*=\s*"([^"]+)"')
    assert frontend == importer, (
        f"frontend/lib/url.ts kent {frontend!r}, de importer schrijft {importer!r}. "
        "Bronlinks vallen dan stil terug op platte tekst."
    )
