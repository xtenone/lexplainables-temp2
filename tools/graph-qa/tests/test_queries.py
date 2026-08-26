"""WP-D: de SPARQL-bouwers produceren de juiste patronen en valideren invoer."""
from __future__ import annotations

import pytest

from agent.graph import queries as q


def test_fts_gebruikt_lucene_en_limit():
    sparql = q.fts("invordering AND belasting", 5)
    assert "inst:bwb_tekst" in sparql
    assert 'luc:query "invordering AND belasting"' in sparql
    assert "LIMIT 5" in sparql


def test_fts_limit_wordt_begrensd():
    assert "LIMIT 50" in q.fts("x", 999)
    assert "LIMIT 1" in q.fts("x", 0)


def test_list_regelingen_filtert_eigen_iri_ruimte():
    sparql = q.list_regelingen()
    assert "a bwb:Regeling" in sparql
    assert 'STRSTARTS(STR(?regeling), "urn:bwb:")' in sparql


def test_get_artikel_bouwt_iri_en_leden():
    sparql = q.get_artikel("BWBR0004770", "9")
    assert "<urn:bwb:BWBR0004770:artikel:9>" in sparql
    assert "bwb:heeftLid" in sparql


def test_get_lid_iri():
    assert "<urn:bwb:BWBR0004770:artikel:9:lid:1>" in q.get_lid("BWBR0004770", "9", "1")


def test_get_lid_levert_de_onderdelen_mee():
    """Een definitielid is zonder zijn onderdelen leeg.

    Artikel 2 lid 1 IW 1990 heeft als eigen tekst alleen "Deze wet verstaat onder:"; de definities
    (a t/m t, waaronder 'belastingschuldige') zitten in de onderdelen. Kwamen die niet mee, dan ging
    de agent het met raw_sparql-pogingen compenseren — acht beurten voor één definitievraag.
    """
    sparql = q.get_lid("BWBR0004770", "2", "1")
    assert "bwb:bevat" in sparql, "onderdelen moeten worden opgehaald"
    assert "GROUP_CONCAT" in sparql, "gebundeld, anders herhaalt de lidtekst per onderdeel"
    assert "ORDER BY ?o" in sparql, "volgorde a, b, c, … moet vastliggen"
    assert "bwb:jci ?oj" in sparql, "elk onderdeel krijgt zijn eigen vindplaats"
    assert 'STRBEFORE(?oj, "&z=")' in sparql, "zonder de datumstaart; die staat al in de lid-jci"


def test_get_artikel_levert_directe_onderdelen_mee():
    """Artikelen zonder leden hebben hun opsomming direct onder het artikel (heeftOnderdeel)."""
    sparql = q.get_artikel("BWBR0019237", "9a")
    assert "bwb:heeftOnderdeel" in sparql
    assert "bwb:heeftLid" in sparql, "de leden blijven ook meekomen"


def test_verwijzingen_met_en_zonder_lid():
    met = q.follow_verwijzingen("BWBR0004770", "9", "1")
    assert ":artikel:9:lid:1>" in met and "bwb:heeftVerwijzing" in met
    zonder = q.follow_verwijzingen("BWBR0004770", "9")
    assert ":artikel:9>" in zonder and ":lid:" not in zonder


def test_referenced_by_gebruikt_verwijzingdoor():
    assert "bwb:verwijzingDoor" in q.referenced_by("BWBR0004770", "9")


def test_count_by_type():
    sparql = q.count_by_type()
    assert "COUNT(DISTINCT ?s)" in sparql
    assert "STRSTARTS" in sparql


def test_context_subgraaf_dekt_alle_relaties():
    sparql = q.context("BWBR0004770", "9")
    # node zelf + structuur + leden + uit-/ingaande verwijzingen in één query
    assert "<urn:bwb:BWBR0004770:artikel:9>" in sparql
    assert "bwb:bevat" in sparql
    assert "bwb:heeftLid" in sparql
    assert "bwb:heeftVerwijzing" in sparql
    assert "bwb:verwijzingDoor" in sparql
    assert "UNION" in sparql


def test_context_lid_gebruikt_lid_iri_maar_verwijzingdoor_op_artikel():
    sparql = q.context("BWBR0004770", "9", "1")
    assert ":artikel:9:lid:1>" in sparql          # node = het lid
    assert "<urn:bwb:BWBR0004770:artikel:9> bwb:verwijzingDoor" in sparql  # incoming op artikel


def test_resolve_begrip_escapet_term():
    # Een aanhalingsteken in de term mag de query niet breken.
    sparql = q.resolve_begrip('dwang"bevel')
    assert '\\"' in sparql
    assert "skos:prefLabel" in sparql


@pytest.mark.parametrize("bad", ["DROP", "BWBR", "', DELETE", "0004770"])
def test_ongeldig_bwb_id_wordt_geweigerd(bad):
    with pytest.raises(ValueError):
        q.get_regeling_info(bad)


@pytest.mark.parametrize("bad", ["9; DROP", "../x", "9 9"])
def test_ongeldig_artikel_wordt_geweigerd(bad):
    with pytest.raises(ValueError):
        q.get_artikel("BWBR0004770", bad)
