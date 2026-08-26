from app.validation import GELDIGE_JAS_KLASSEN


def test_jas_klassen_canoniek():
    assert "Rechtssubject" in GELDIGE_JAS_KLASSEN
    assert len(GELDIGE_JAS_KLASSEN) == 13
