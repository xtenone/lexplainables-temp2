"""Robuuste JAS-JSON-parser (_parse_elementen) — de grounding-helper die de annoteer-stap gebruikt."""
from __future__ import annotations

import json

from agent.annotatie import _parse_elementen, _verwerk


def test_parse_fenced_json():
    txt = '```json\n{"elementen": [{"klasse": "Rechtssubject", "tekst": "de ontvanger"}]}\n```'
    els = _parse_elementen(txt)
    assert len(els) == 1 and els[0]["klasse"] == "Rechtssubject"


def test_parse_proza_rondom_json():
    txt = 'Hier is mijn analyse:\n{"elementen": [{"klasse": "Voorwaarde", "tekst": "indien"}]}\nEinde.'
    els = _parse_elementen(txt)
    assert len(els) == 1 and els[0]["tekst"] == "indien"


def test_parse_afgekapt_salvaget_complete_elementen():
    # geldig element 1 (compleet), element 2 afgekapt op max_tokens (geen sluit-}) → salvage houdt 1.
    txt = (
        '{"elementen": [{"klasse": "Rechtssubject", "tekst": "de ontvanger", "toelichting": "wie"}, '
        '{"klasse": "Rechtsbetrekking", "tekst": "kan uitstel'
    )
    els = _parse_elementen(txt)
    assert len(els) == 1 and els[0]["klasse"] == "Rechtssubject"


def test_parse_alternatieven_niet_als_element():
    # een genest Alternatief-object (klasse+motivatie, geen tekst) telt niet als element.
    txt = (
        '{"elementen": [{"klasse": "Rechtsfeit", "tekst": "indienen", '
        '"alternatieven": [{"klasse": "Rechtsbetrekking", "motivatie": "twijfel"}]}]}'
    )
    els = _parse_elementen(txt)
    assert len(els) == 1 and els[0]["klasse"] == "Rechtsfeit"


# --- grounding: id's toekennen en verworpen fragmenten teruggeven -------------------------------

from agent.annotatie import _verwerk, _verwerk_critic  # noqa: E402

CORPUS = "De ontvanger kan uitstel van betaling verlenen indien de belastingschuldige in gebreke is."


def test_verwerk_kent_ids_toe_en_grondt():
    txt = '{"elementen": [{"klasse": "Rechtssubject", "tekst": "De ontvanger"}]}'
    voorstellen, verworpen = _verwerk(txt, CORPUS, "BWBR1", "9")
    assert len(voorstellen) == 1 and not verworpen
    assert voorstellen[0].id and len(voorstellen[0].id) == 12
    assert voorstellen[0].grounded is True


def test_verwerk_behoudt_een_meegegeven_id():
    """Een herziening levert dezelfde elementen opnieuw; het id moet dan blijven staan, anders
    matcht de api ze als nieuw en verliest de jurist zijn beslissingen."""
    txt = '{"elementen": [{"id": "vast12345678", "klasse": "Rechtssubject", "tekst": "De ontvanger"}]}'
    voorstellen, _ = _verwerk(txt, CORPUS, "BWBR1", "9")
    assert voorstellen[0].id == "vast12345678"


def test_verwerk_geeft_verworpen_fragmenten_terug_met_reden():
    txt = (
        '{"elementen": ['
        '{"klasse": "Rechtssubject", "tekst": "De ontvanger"},'
        '{"klasse": "Voorwaarde", "tekst": "een zin die hier niet staat"},'
        '{"klasse": "Verzonnen", "tekst": "De ontvanger"}]}'
    )
    voorstellen, verworpen = _verwerk(txt, CORPUS, "BWBR1", "9")
    assert len(voorstellen) == 1
    redenen = {v.reden for v in verworpen}
    assert redenen == {"niet_letterlijk", "ongeldige_klasse"}
    # De tekst gaat mee terug: dát is wat een herziening kan repareren.
    niet_letterlijk = next(v for v in verworpen if v.reden == "niet_letterlijk")
    assert niet_letterlijk.tekst == "een zin die hier niet staat"


def test_critic_koppelt_op_id():
    txt = '{"oordelen": [{"id": "abc123", "aandacht": "rood", "motivatie": "fout", "actie": "verwijder"}]}'
    oordelen, _ = _verwerk_critic(txt, ["abc123", "def456"])
    assert set(oordelen) == {"abc123"}
    assert oordelen["abc123"].actie == "verwijder"


def test_critic_valt_terug_op_index_als_het_id_ontbreekt():
    """Een model dat het id-veld vergeet mag niet stilzwijgend álle oordelen verliezen."""
    txt = '{"oordelen": [{"index": 1, "aandacht": "geel", "motivatie": "twijfel"}]}'
    oordelen, _ = _verwerk_critic(txt, ["abc123", "def456"])
    assert set(oordelen) == {"def456"}


def test_critic_negeert_onbekende_ids_en_ongeldige_aandacht():
    txt = (
        '{"oordelen": ['
        '{"id": "bestaat-niet", "aandacht": "rood", "motivatie": "x"},'
        '{"id": "abc123", "aandacht": "paars", "motivatie": "x"}]}'
    )
    oordelen, _ = _verwerk_critic(txt, ["abc123"])
    assert oordelen == {}


def test_verwijderen_mag_alleen_bij_rood():
    """Weggooien is de zwaarste ingreep; bij twijfel wordt het hooguit een vervanging."""
    txt = ('{"oordelen": [{"id": "a", "aandacht": "geel", "motivatie": "hm", "actie": "verwijder",'
           ' "voorstel_klasse": "Voorwaarde"}]}')
    oordelen, _ = _verwerk_critic(txt, ["a"])
    assert oordelen["a"].actie == "vervang"


def test_vervangen_zonder_voorstel_is_geen_instructie():
    """'Vervang dit' zonder te zeggen waardoor is een klacht, geen opdracht — dan behouden."""
    txt = '{"oordelen": [{"id": "a", "aandacht": "rood", "motivatie": "niet goed", "actie": "vervang"}]}'
    oordelen, _ = _verwerk_critic(txt, ["a"])
    assert oordelen["a"].actie == "behoud"


def test_critic_negeert_een_verzonnen_voorstel_klasse():
    txt = ('{"oordelen": [{"id": "a", "aandacht": "rood", "motivatie": "x", "actie": "vervang",'
           ' "voorstel_klasse": "Onzin", "voorstel_tekst": "De ontvanger"}]}')
    oordelen, _ = _verwerk_critic(txt, ["a"])
    assert oordelen["a"].voorstel_klasse == ""
    assert oordelen["a"].voorstel_tekst == "De ontvanger"


def test_ontbrekend_neemt_een_letterlijk_fragment_mee():
    txt = ('{"oordelen": [], "ontbrekend": [{"klasse": "Voorwaarde", "reden": "conditie",'
           ' "tekst": "indien de belastingschuldige in gebreke is"}]}')
    _, ontbrekend = _verwerk_critic(txt, [])
    assert ontbrekend[0].tekst == "indien de belastingschuldige in gebreke is"


CORPUS = "De ontvanger verleent uitstel van betaling indien de schuldenaar daarom verzoekt."


def _json(elementen):
    return json.dumps({"elementen": elementen})


def test_hetzelfde_fragment_twee_keer_levert_een_element():
    """Herhaalt het model zich binnen één ronde, dan krijgt de jurist anders twee gelijke kaartjes."""
    voorstellen, _ = _verwerk(_json([
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
        {"klasse": "Rechtssubject", "tekst": "De  ontvanger", "lid": "1"},   # andere spatiëring
    ]), CORPUS, "BWBR0004770", "9")
    assert len(voorstellen) == 1


def test_het_eerste_voorkomen_wint_want_dat_draagt_het_id():
    """Aan het id uit een eerdere ronde hangen de beslissingen van de jurist."""
    voorstellen, _ = _verwerk(_json([
        {"id": "el-oud", "klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
    ]), CORPUS, "BWBR0004770", "9")
    assert [v.id for v in voorstellen] == ["el-oud"]


def test_zelfde_fragment_in_een_andere_klasse_wordt_een_alternatief():
    """Twijfel tussen twee klassen op hetzelfde fragment is legitiem — maar één markering.

    Dit stond eerder omgekeerd (twee losse voorstellen), doordat de ontdubbelsleutel de klasse
    meetelde. Die sleutel liep daarmee uit de pas met de api, die bewust op tekst + lid matcht: een
    herziening die alleen herclassificeerde werd daar een tweede element naast het origineel, en de
    jurist zag dezelfde span twee keer met tegenstrijdige klassen. Eén klasse per element, de tweede
    lezing als alternatief — zie `tests/test_ontdubbelsleutel.py` voor de volledige regel.
    """
    voorstellen, _ = _verwerk(_json([
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
        {"klasse": "Rechtsobject", "tekst": "De ontvanger", "lid": "1"},
    ]), CORPUS, "BWBR0004770", "9")
    assert len(voorstellen) == 1
    assert voorstellen[0].klasse == "Rechtssubject"
    assert [a.klasse for a in voorstellen[0].alternatieven] == ["Rechtsobject"]


# --- Een id uit het model is geen vrijbrief -------------------------------------------------------

def test_herziening_negeert_een_id_dat_niet_is_aangeboden():
    """Een verwisseld of verzonnen id zou anders een ánder element overschrijven — met de
    beslissingen van de jurist en het auditspoor die eraan hangen."""
    corpus = "De ontvanger verleent uitstel van betaling."
    llm = json.dumps({"elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1",
         "id": "id-van-een-ander-element"},
    ]})

    voorstellen, _ = _verwerk(llm, corpus, "BWBR0004770", "9", "1", geldige_ids={"id-a", "id-b"})

    assert len(voorstellen) == 1
    assert voorstellen[0].id not in ("id-van-een-ander-element", "id-a", "id-b")
    assert len(voorstellen[0].id) == 12, "een vers id, zoals bij een nieuw element"


def test_herziening_behoudt_een_id_dat_wel_is_aangeboden():
    corpus = "De ontvanger verleent uitstel van betaling."
    llm = json.dumps({"elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1", "id": "id-a"},
    ]})

    voorstellen, _ = _verwerk(llm, corpus, "BWBR0004770", "9", "1", geldige_ids={"id-a", "id-b"})

    assert voorstellen[0].id == "id-a", "hierop hangen de beslissingen en het auditspoor"


def test_zonder_geldige_ids_blijft_het_oude_gedrag():
    """De eerste ronde geeft de set niet mee: daar is nog geen element om te overschrijven."""
    corpus = "De ontvanger verleent uitstel van betaling."
    llm = json.dumps({"elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1", "id": "el-a"},
    ]})

    voorstellen, _ = _verwerk(llm, corpus, "BWBR0004770", "9", "1")

    assert voorstellen[0].id == "el-a"
