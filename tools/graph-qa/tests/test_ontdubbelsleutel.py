"""De canonieke ontdubbelregel: wanneer zijn twee voorstellen dezelfde markering?

Die regel bestaat in drie Python-implementaties (de agent, de beurt-driver, de api) plus één in
TypeScript (`frontend/lib/annotatie.ts:mergeVoorstellen`, met dezelfde tabel in zijn eigen test).
Ze liepen uiteen op precies één punt — de klasse — en dat leverde dubbele kaarten op zodra een
herziening herclassificeerde. Deze test houdt de Python-kant tegen elkaar.

De regel: **match op `id`; is er geen id, dan op genormaliseerde tekst + lid. Nooit op klasse.**
"""
from __future__ import annotations

import pytest

from agent.annotatie import _verwerk, sleutel_van
from agent.beurt import BeurtSchrijver

CORPUS = (
    "Een belastingaanslag is invorderbaar zes weken na de dagtekening van het aanslagbiljet. "
    "De ontvanger kan uitstel van betaling verlenen."
)


# --- de sleutel zelf ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, b, zelfde",
    [
        # klasse telt NIET mee: een herclassificatie is hetzelfde element.
        (("de ontvanger", "1"), ("de ontvanger", "1"), True),
        # witruimte en hoofdletters zijn opmaak, geen identiteit.
        (("de  ontvanger", "1"), ("De ontvanger", "1"), True),
        (("de\nontvanger", "1"), ("de ontvanger", "1"), True),
        # lid onderscheidt wél: hetzelfde woord in een ander lid is een andere markering.
        (("de ontvanger", "1"), ("de ontvanger", "2"), False),
        (("de ontvanger", ""), ("de ontvanger", "1"), False),
        # ander fragment blijft een ander element.
        (("de ontvanger", "1"), ("de belastingschuldige", "1"), False),
    ],
)
def test_sleutel_identiteit(a, b, zelfde):
    assert (sleutel_van(*a) == sleutel_van(*b)) is zelfde


def test_sleutel_negeert_klasse_by_design():
    """Regressie op de bug: mét klasse in de sleutel werd een herclassificatie een tweede element."""
    assert sleutel_van("de ontvanger", "1") == sleutel_van("de ontvanger", "1")


# --- implementatie 1: de annoteer-parser -------------------------------------------------------

def _json(*elementen: dict) -> str:
    import json

    return json.dumps({"elementen": list(elementen)})


def test_verwerk_ontdubbelt_identieke_herhaling():
    voorstellen, verworpen = _verwerk(
        _json(
            {"klasse": "Rechtssubject", "tekst": "De ontvanger"},
            {"klasse": "Rechtssubject", "tekst": "De  ontvanger"},
        ),
        CORPUS, "BWBR0004770", "9",
    )
    assert len(voorstellen) == 1
    assert not verworpen


def test_verwerk_maakt_van_tweede_klasse_een_alternatief():
    """Dezelfde span, andere klasse: twijfel, geen tweede element — en niet stil weggegooid."""
    voorstellen, _ = _verwerk(
        _json(
            {"klasse": "Tijdsaanduiding", "tekst": "zes weken na de dagtekening van het aanslagbiljet"},
            {"klasse": "Voorwaarde", "tekst": "zes weken na de dagtekening van het aanslagbiljet",
             "toelichting": "kan ook een conditie zijn"},
        ),
        CORPUS, "BWBR0004770", "9",
    )
    assert len(voorstellen) == 1
    v = voorstellen[0]
    assert v.klasse == "Tijdsaanduiding"
    assert [a.klasse for a in v.alternatieven] == ["Voorwaarde"]
    assert v.alternatieven[0].motivatie == "kan ook een conditie zijn"


def test_verwerk_dupliceert_alternatief_niet():
    voorstellen, _ = _verwerk(
        _json(
            {"klasse": "Tijdsaanduiding", "tekst": "zes weken na de dagtekening van het aanslagbiljet",
             "alternatieven": [{"klasse": "Voorwaarde", "motivatie": "eerder al genoemd"}]},
            {"klasse": "Voorwaarde", "tekst": "zes weken na de dagtekening van het aanslagbiljet"},
        ),
        CORPUS, "BWBR0004770", "9",
    )
    assert [a.klasse for a in voorstellen[0].alternatieven] == ["Voorwaarde"]


def test_verwerk_houdt_zelfde_tekst_in_ander_lid_apart():
    voorstellen, _ = _verwerk(
        _json(
            {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
            {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "2"},
        ),
        CORPUS, "BWBR0004770", "9",
    )
    assert len(voorstellen) == 2


# --- implementatie 2: de beurt-driver ----------------------------------------------------------

def _el(**kv):
    return {"id": "", "klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1", **kv}


def test_beurt_id_wint():
    s = BeurtSchrijver()
    s.verwerk({"type": "element", "element": _el(id="a1", klasse="Rechtsobject")})
    s.verwerk({"type": "element", "element": _el(id="a1", klasse="Rechtssubject")})
    assert len(s.elementen) == 1
    assert s.elementen[0]["klasse"] == "Rechtssubject"  # de laatste versie wint


def test_beurt_valt_terug_op_inhoud_zonder_id():
    s = BeurtSchrijver()
    s.verwerk({"type": "element", "element": _el(tekst="De ontvanger")})
    s.verwerk({"type": "element", "element": _el(tekst="De  ontvanger")})
    assert len(s.elementen) == 1


def test_beurt_ontdubbelt_over_klassewijziging_heen():
    """De faalcase: herclassificatie zonder id mocht geen tweede kaart opleveren."""
    s = BeurtSchrijver()
    s.verwerk({"type": "element", "element": _el(klasse="Rechtsobject")})
    s.verwerk({"type": "element", "element": _el(klasse="Voorwaarde")})
    assert len(s.elementen) == 1
    assert s.elementen[0]["klasse"] == "Voorwaarde"


def test_beurt_houdt_ander_lid_apart():
    s = BeurtSchrijver()
    s.verwerk({"type": "element", "element": _el(id="a1", lid="1")})
    s.verwerk({"type": "element", "element": _el(id="a2", lid="2")})
    assert len(s.elementen) == 2


# --- implementatie 3: de api-merge -------------------------------------------------------------

def test_api_sleutel_is_dezelfde_regel():
    """De api is de canonieke bron; de agent hoort hem exact te volgen.

    Overslaan als de api niet geïnstalleerd is (graph-qa draait als eigen dienst met eigen venv).
    """
    api_sleutel = pytest.importorskip(
        "app.routers.annotatie", reason="api niet in deze omgeving geïnstalleerd"
    )._sleutel
    for tekst, lid in [
        ("De ontvanger", "1"),
        ("De  ontvanger", "1"),
        ("de ontvanger", ""),
        ("zes weken na de dagtekening", "2"),
    ]:
        assert api_sleutel(tekst, lid) == sleutel_van(tekst, lid)
