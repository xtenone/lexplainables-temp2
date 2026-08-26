"""PR 2.1: grounding-verificatie en bron-curatie."""
from __future__ import annotations

from agent.grounding import check_grounding, curate_sources
from agent.models import Source
from agent.provenance import citations_in, iter_refs

IW = "urn:bwb:BWBR0004770:artikel:9"
LEIDRAAD = "urn:bwb:BWBR0024096:artikel:26"


def _trace(text: str):
    return [("get_artikel", text)]


def test_citatie_in_trace_is_grounded():
    answer = "Zie artikel 9 van de Invorderingswet 1990 (BWBR0004770)."
    report = check_grounding(answer, _trace(f"<{IW}> bwb:tekst '...' ."))
    assert report.grounded is True
    assert report.unsupported == []


def test_verzonnen_citatie_wordt_gemarkeerd():
    answer = "Zie de niet-bestaande regeling BWBR9999999."
    report = check_grounding(answer, _trace(f"<{IW}>"))
    assert report.grounded is False
    assert any("BWBR9999999" in u for u in report.unsupported)


def test_grounding_op_bwb_granulariteit_geen_vals_alarm():
    # Antwoord noemt een jci met afwijkende opmaak; BWB-id staat wél in de trace → geen alarm.
    answer = "Vindplaats: jci1.3:c:BWBR0004770&artikel=9&lid=1"
    report = check_grounding(answer, _trace("resultaat met BWBR0004770 erin"))
    assert report.grounded is True


def test_prefix_bwb_wordt_niet_vals_gegrond():
    # L1: het antwoord noemt een prefix-id (BWBR0001) van het opgehaalde BWBR00012345. Exacte match
    # (geen substring) → terecht ongegrond.
    report = check_grounding("Volgens BWBR0001 geldt de termijn.", _trace("resultaat met BWBR00012345 erin"))
    assert report.grounded is False
    assert any("BWBR0001" in u for u in report.unsupported)


def test_curate_prefix_bwb_wordt_niet_meegesleept():
    # L1: een bron met langer id mag niet meeliften op een genoemde prefix-id.
    langer = "urn:bwb:BWBR00012345:artikel:1"
    sources = [Source(label=langer, uri=langer), Source(label=IW, uri=IW)]
    kept = [s.uri for s in curate_sources(sources, "Zie BWBR0001 en de Invorderingswet (BWBR0004770).")]
    assert IW in kept
    assert langer not in kept


def test_curate_beperkt_tot_genoemde_regeling():
    sources = [
        Source(label=IW, uri=IW),
        Source(label=LEIDRAAD, uri=LEIDRAAD),
    ]
    answer = "Alleen de Invorderingswet 1990 (BWBR0004770) is relevant."
    kept = curate_sources(sources, answer)
    uris = [s.uri for s in kept]
    assert IW in uris
    assert LEIDRAAD not in uris  # niet genoemde regeling valt weg


def test_curate_valt_terug_op_alles_zonder_bwb_in_antwoord():
    sources = [Source(label=IW, uri=IW)]
    kept = curate_sources(sources, "Een antwoord zonder enig BWB-id.")
    assert kept == sources


def test_jci_backslash_wordt_gestript():
    text = r'"jci1.3:c:BWBR0004770&artikel=9&z=2026-07-01\ " staat hier'
    uris = [uri for uri, _, jci in iter_refs(text) if jci]
    assert uris
    assert not any(u.endswith("\\") for u in uris)


def test_citations_in_negeert_vocabulaire_namespace():
    assert citations_in("?s <urn:bwb-ns:heeftLid> ?o") == []


# --- Niveau: gegrond / onbepaald / ongegrond -----------------------------------------------------
#
# `grounded` was een bool, en "geen enkele verwijzing genoemd" viel daarmee in dezelfde bak als
# "alles gecontroleerd en in orde". Dat is de gevaarlijkste soort meting: de afwezigheid van bewijs
# telde als bewijs van afwezigheid.

def test_antwoord_zonder_vindplaats_is_onbepaald_niet_gegrond():
    report = check_grounding(
        "De aanslag is invorderbaar zes weken na de dagtekening.",
        _trace(f"<{IW}> bwb:tekst 'iets' ."),
    )
    assert report.niveau == "onbepaald"
    assert report.cited == []
    # De bool blijft doen wat hij deed (er is niets AANGETROFFEN dat niet klopt) — het onderscheid
    # zit in het niveau, zodat de weergave er iets anders van kan maken dan groen.
    assert report.grounded is True


def test_gecontroleerde_verwijzing_is_gegrond():
    report = check_grounding("Zie BWBR0004770, artikel 9.", _trace("resultaat met BWBR0004770"))
    assert report.niveau == "gegrond"


def test_verzonnen_verwijzing_is_ongegrond():
    report = check_grounding("Zie BWBR9999999.", _trace("resultaat met BWBR0004770"))
    assert report.niveau == "ongegrond"


# --- Citaatcontrole ------------------------------------------------------------------------------
#
# De agent belooft letterlijk te citeren, en de annotatieketen dwingt dat af. In het antwoordpad
# ontbrak die controle: een citaat met één woord verschil passeerde ongemerkt.

WETTEKST = _trace(
    "?lidtekst\nEen belastingaanslag is invorderbaar zes weken na de dagtekening van het aanslagbiljet."
)


def test_letterlijk_citaat_passeert():
    report = check_grounding(
        'De wet zegt: "Een belastingaanslag is invorderbaar zes weken na de dagtekening".',
        WETTEKST,
    )
    assert report.niet_letterlijk == []
    assert report.niveau == "gegrond" or report.niveau == "onbepaald"


def test_bijna_letterlijk_citaat_wordt_gemarkeerd():
    report = check_grounding(
        'De wet zegt: "Een belastingaanslag is invorderbaar binnen zes weken na de dagtekening".',
        WETTEKST,
    )
    assert report.niet_letterlijk, "een ingevoegd woord hoort op te vallen"
    assert report.niveau == "ongegrond"
    assert report.grounded is False


def test_citaat_met_afwijkende_witruimte_is_geen_afwijking():
    # Dezelfde normalisatie als bij een JAS-markering: layout mag verschillen, woorden niet.
    report = check_grounding(
        'Er staat:  "Een belastingaanslag   is invorderbaar\nzes weken na de dagtekening".',
        WETTEKST,
    )
    assert report.niet_letterlijk == []


def test_kort_aangehaald_begrip_wordt_niet_gecontroleerd():
    # "belastingschuldige" tussen quotes is een begrip, geen citaat van een passage. Daarop
    # controleren levert vals alarm bij elke verbuiging.
    report = check_grounding('Het begrip "de belastingschuldige" komt hier terug.', WETTEKST)
    assert report.niet_letterlijk == []
    assert report.niveau == "onbepaald"


# --- wat de tijdlijn erover zegt ------------------------------------------------------------------

def test_rapport_telt_hoeveel_citaten_zijn_nagelopen():
    """Zonder dat getal is niet te melden wát er is gecontroleerd."""
    answer = 'Er staat: "De ontvanger verleent uitstel van betaling" en "dat is de regel hier".'
    report = check_grounding(answer, _trace("De ontvanger verleent uitstel van betaling."))
    assert report.citaten == 2
    assert report.niet_letterlijk == ["dat is de regel hier"]


def test_melding_noemt_de_citaten_als_er_geen_vindplaats_is():
    """Het geval dat op dev misging: artikelen in gewone taal, dus nul vindplaatsen — maar wél twee
    citaten die allebei klopten. De tijdlijn meldde toen "0 verwijzingen onderbouwd", wat leest als
    een mislukte controle terwijl er juist iets gecontroleerd én goed bevonden was."""
    from agent.orchestrator import _grounding_melding

    answer = (
        'Volgens artikel 2 lid 1 onderdeel m geldt: "De ontvanger verleent uitstel van betaling" '
        'en verderop "indien de schuldenaar daarom verzoekt".'
    )
    bron = "De ontvanger verleent uitstel van betaling indien de schuldenaar daarom verzoekt."
    report = check_grounding(answer, _trace(bron))

    assert report.cited == [] and report.niveau == "gegrond"
    assert _grounding_melding(report) == "brongetrouwheid: 2 citaten gecontroleerd"


def test_melding_zwijgt_niet_als_er_niets_te_controleren_viel():
    from agent.orchestrator import _grounding_melding

    report = check_grounding("Dat staat niet in de kennisgraaf.", _trace("iets anders"))
    assert report.niveau == "onbepaald"
    assert "niets te controleren" in _grounding_melding(report)


def test_melding_noemt_beide_soorten_als_ze_er_allebei_zijn():
    from agent.orchestrator import _grounding_melding

    answer = f'Zie {IW} (BWBR0004770): "De ontvanger verleent uitstel van betaling".'
    bron = f"<{IW}> bwb:tekst 'De ontvanger verleent uitstel van betaling.' ."
    melding = _grounding_melding(check_grounding(answer, _trace(bron)))
    assert "verwijzing" in melding and "1 citaat" in melding and "gecontroleerd" in melding
