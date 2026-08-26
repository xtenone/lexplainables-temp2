from app.validation import (
    GELDIGE_JAS_KLASSEN,
    brongetrouwheid_check,
    normaliseer,
    schema_check,
)


def _a2(leden, markeringen, bronref="jci:x"):
    """Bouw een act-2-analyse (werkgebied met één bron) rond leden + markeringen."""
    return {"werkgebied": {"naam": "test"}, "bronnen": [{
        "bron_id": "br1", "label": "Testwet art. 1", "bronreferentie": bronref,
        "leden": leden, "markeringen": markeringen, "verwijzingen": [],
    }]}


def test_jas_klassen_canoniek():
    assert "Rechtssubject" in GELDIGE_JAS_KLASSEN
    assert len(GELDIGE_JAS_KLASSEN) == 13


def test_schema_check_delegatie_ongeldige_klasse():
    data = _a2([], [{"id": "m1", "bron_id": "br1", "klasse": "Verzonnen"}])
    fouten, _ = schema_check(data, "2")
    assert any("Ongeldige JAS-klasse" in f for f in fouten)


def test_brongetrouwheid_citaat_normalisatie():
    leden = [{"lid": "1", "tekst": "De  belastingplichtige doet “aangifte”."}]
    # zelfde citaat met rechte quotes en enkele spatie → moet als letterlijk gelden
    ok = _a2(leden, [{"id": "m1", "formulering": 'De belastingplichtige doet "aangifte".',
                      "vindplaats": "lid 1"}])
    assert brongetrouwheid_check(ok, "2") == []

    verzonnen = _a2(leden, [{"id": "m1", "formulering": "iets dat er niet staat",
                             "vindplaats": "lid 1"}])
    schend = brongetrouwheid_check(verzonnen, "2")
    assert any("letterlijk citaat" in s for s in schend)


def test_brongetrouwheid_citaat_unicode_nfc_nfd():
    """Visueel identieke tekst in verschillende unicode-composities (compose e-acute U+00E9 vs
    decompose e + combining acute U+0065 U+0301) moet als letterlijk citaat gelden -- anders
    faalt een terechte markering de HARD-check. Escapes zijn expliciet zodat de toets de
    NFC-normalisatie echt uitoefent (een editor zou anders een vorm afdwingen)."""
    nfc = "Het pr\u00e9-advies"
    nfd = "Het pre\u0301-advies"
    assert nfc != nfd  # bytes verschillen; visueel identiek
    # Bronlid decompose, markering compose.
    bron_nfd = _a2([{"lid": "1", "tekst": nfd + " van de commissie."}],
                   [{"id": "m1", "formulering": nfc, "vindplaats": "lid 1"}])
    assert brongetrouwheid_check(bron_nfd, "2") == []
    # En omgekeerd: bronlid compose, markering decompose.
    bron_nfc = _a2([{"lid": "1", "tekst": nfc + " van de commissie."}],
                   [{"id": "m1", "formulering": nfd, "vindplaats": "lid 1"}])
    assert brongetrouwheid_check(bron_nfc, "2") == []


def test_brongetrouwheid_citeerconventies_beletsel_en_haken():
    # Echte casus: art. 7a lid 1 Invorderingswet 1990. De skill mag beletselteken (...) voor
    # geelideerde tussentekst en vierkante haken ([...]) voor een invoeging gebruiken; de harde
    # check moet die — net als de zachte skill-check — als letterlijk citaat accepteren.
    leden = [{"lid": "1", "tekst": (
        "In afwijking van artikel 4:89, eerste lid, van de Algemene wet bestuursrecht vindt "
        "uitbetaling aan de belastingschuldige van inkomstenbelasting uitsluitend plaats op een "
        "daartoe door de belastingschuldige bestemde bankrekening. De belastingschuldige kan niet "
        "meer dan een bankrekening bestemmen voor de uitbetaling van inkomstenbelasting en voor de "
        "in artikel 25 van de Algemene wet inkomensafhankelijke regelingen bedoelde uitbetaling."
    )}]

    def _check(formulering):
        return brongetrouwheid_check(
            _a2(leden, [{"id": "m1", "formulering": formulering, "vindplaats": "lid 1"}]), "2",
        )

    # beletselteken (vgl. m11/m12): geelideerde tussentekst
    assert _check(
        "voor de uitbetaling van inkomstenbelasting en voor de in artikel 25 ... bedoelde uitbetaling"
    ) == []
    # vierkante-haak-invoeging (vgl. m10): toetst op 'een'
    assert _check("een [bankrekening]") == []
    # beletselteken mét normalisatie-ruis: typografische quote + dubbele spatie rond '…'
    assert _check("vindt uitbetaling  …  uitsluitend plaats") == []

    # echte parafrase (vgl. m6): woorden uit het midden weggelaten ZONDER beletselteken
    schend = _check("vindt uitsluitend plaats")
    assert any("letterlijk citaat" in s for s in schend)


def test_brongetrouwheid_markering_over_verwijzing_link():
    # De MCP levert de lid-tekst met intref/extref als inline-Markdown-link. Een markering
    # citeert het zichtbare label; de check moet dat als letterlijk citaat accepteren.
    leden = [{"lid": "1", "tekst": (
        "In afwijking van [artikel 4:89, eerste lid, van de Algemene wet bestuursrecht]"
        "(jci1.3:c:BWBR0005537&artikel=4:89) vindt uitbetaling aan de belastingschuldige van "
        "inkomstenbelasting uitsluitend plaats op een daartoe door de belastingschuldige bestemde "
        "bankrekening. De belastingschuldige kan niet meer dan één bankrekening bestemmen voor de "
        "in [artikel 25 van de Algemene wet inkomensafhankelijke regelingen]"
        "(jci1.3:c:BWBR0018472&artikel=25) bedoelde uitbetaling."
    )}]

    def _check(formulering):
        return brongetrouwheid_check(
            _a2(leden, [{"id": "m1", "formulering": formulering, "vindplaats": "lid 1"}]), "2",
        )

    # markering loopt over de eerste link heen (vgl. m1)
    assert _check("In afwijking van artikel 4:89, eerste lid, van de Algemene wet bestuursrecht") == []
    # markering loopt over de tweede link heen (vgl. m10)
    assert _check(
        "in artikel 25 van de Algemene wet inkomensafhankelijke regelingen bedoelde uitbetaling"
    ) == []
    # genuine parafrase (vgl. m4: woorden uit het midden weggelaten zonder beletselteken) → schending
    schend = _check("vindt uitsluitend plaats op een daartoe door de belastingschuldige bestemde bankrekening")
    assert any("letterlijk citaat" in s for s in schend)


def test_brongetrouwheid_bronreferentie_en_vindplaats_verplicht():
    schend = brongetrouwheid_check(
        _a2([], [{"id": "m1", "formulering": ""}], bronref=""), "2",
    )
    assert any("Bronreferentie" in s for s in schend)
    assert any("Vindplaats" in s for s in schend)


def test_normaliseer():
    assert normaliseer("  A’B  \n c ") == "a'b c"


def test_schema_check_filtert_overlap_met_hard():
    """De zachte citaat/vindplaats-waarschuwingen worden onderdrukt; de harde check dekt ze.

    Zo verschijnt per concern nog precies één melding in de review i.p.v. twee bijna-gelijke.
    """
    data = _a2(
        [{"lid": "1", "tekst": "De belastingplichtige doet aangifte."}],
        [{"id": "m1", "klasse": "Rechtssubject", "formulering": "iets dat er niet staat"}],
    )
    _, waarschuwingen = schema_check(data, "2")
    assert not any("letterlijk citaat" in w for w in waarschuwingen)
    assert not any("vindplaats" in w for w in waarschuwingen)

    # De harde check blijft de schendingen wél melden (precies één per concern).
    schend = brongetrouwheid_check(data, "2")
    assert any("letterlijk citaat" in s for s in schend)
    assert any("Vindplaats" in s for s in schend)


def test_schema_check_act3_filtert_vindplaats():
    data = {"werkgebied": {"naam": "test"}, "bronnen": [{"bron_id": "br1", "label": "x"}],
            "begrippen": [{"id": "b1", "naam": "x", "klasse": "Rechtssubject", "definitie": "y",
                           "vindplaatsen": [{"bron_id": "br1", "lid": "1"}]}]}
    _, waarschuwingen = schema_check(data, "3")
    assert not any("vindplaats" in w.lower() for w in waarschuwingen)
