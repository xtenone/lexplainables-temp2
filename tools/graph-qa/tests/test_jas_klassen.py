"""JAS-klassen-referentie: 13 canonieke klassen, drift-guard, volledigheid."""
from __future__ import annotations

from agent.jas_klassen import GELDIGE_JAS_KLASSEN, JAS_KLASSEN, JAS_KLASSEN_VOLGORDE

# De canonieke JAS-namen + weergave-volgorde (docs/wetsanalyse/wa-table.png). Deze test is de drift-guard:
# wijzigen van een naam moet bewust gebeuren en gelijk blijven met de rest van het systeem
# (validation.JAS_KLASSEN_VOLGORDE in het api-/skill-spoor).
VERWACHT: tuple[str, ...] = (
    "Rechtssubject",
    "Rechtsobject",
    "Rechtsbetrekking",
    "Rechtsfeit",
    "Voorwaarde",
    "Afleidingsregel",
    "Variabele en variabelewaarde",
    "Parameter en parameterwaarde",
    "Operator",
    "Tijdsaanduiding",
    "Plaatsaanduiding",
    "Delegatiebevoegdheid en delegatie-invulling",
    "Brondefinitie",
)


def test_dertien_canonieke_klassen():
    assert JAS_KLASSEN_VOLGORDE == VERWACHT
    assert len(JAS_KLASSEN) == 13
    assert GELDIGE_JAS_KLASSEN == frozenset(VERWACHT)


def test_elke_klasse_volledig_geduid():
    for k in JAS_KLASSEN:
        assert k.naam and k.omschrijving and k.vraag and k.uitdrukkingswijze
