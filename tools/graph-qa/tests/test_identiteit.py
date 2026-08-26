"""De agent heet Lex en kadert zichzelf als hulpmiddel.

Geen stijlpolitie: deze test bewaakt drie dingen die stil kunnen sneuvelen bij een prompt-herschrijving.
(1) De naam staat erin — zonder naam kan Lex zich niet voorstellen en valt hij terug op "ik ben een AI".
(2) De kadering staat erin (voorstel / de jurist beslist / geen juridisch advies). Dat is niet
    cosmetisch: het platform draait op "de AI produceert, de mens beoordeelt", en een naam plus een
    avatar maakt van een hulpmiddel makkelijk een adviseur.
(3) Elke specialist érft hem, want de specialisten stapelen hun focus bovenop SYSTEM_PROMPT — dat is de
    hele reden dat de identiteit daar staat en niet per specialist.
"""
from __future__ import annotations

from agent import specialists
from agent.prompts import SYSTEM_PROMPT


def test_prompt_noemt_de_naam():
    assert "Lex" in SYSTEM_PROMPT


def test_prompt_kadert_lex_als_hulpmiddel():
    laag = SYSTEM_PROMPT.lower()
    assert "hulpmiddel" in laag
    assert "voorstel" in laag
    assert "beslist" in laag
    assert "geen juridisch advies" in laag


def test_prompt_stelt_zich_alleen_op_verzoek_voor():
    # Zonder deze rem begint elk antwoord met een introductie; de werkplek toont de korte
    # zelfbeschrijving al in zijn lege staat.
    assert "alleen op verzoek" in SYSTEM_PROMPT.lower()


def test_alle_specialisten_erven_de_identiteit():
    # De samenvoeging zelf (orchestrator: SYSTEM_PROMPT + spec.system) is wat de erving oplevert;
    # een specialist die zijn eigen identiteit meebrengt zou hier twee namen naast elkaar zetten.
    for naam, spec in specialists.SPECIALISTS.items():
        samengesteld = SYSTEM_PROMPT + (f"\n\n{spec.system}" if spec.system else "")
        assert "Lex" in samengesteld, naam


def test_prompt_verbiedt_zelfbedachte_jas_klassen():
    """De antwoordroute mag geen JAS-klassen voorstellen.

    Op dev zette de `algemeen`-specialist onder een uitleg een lijstje "voorgestelde JAS-klassen"
    met labels als `art36-IW` en `betalingsonmacht-melding` — die bestaan niet; de dertien staan
    vast. De klassecontrole (`_verwerk`) zit alléén in de annotatieroute, dus hier is de prompt de
    enige rem. De identiteitsregel noemt markeren wél als iets wat Lex doet, en dat las het model
    als uitnodiging; deze grens hoort daar dus expliciet naast te staan.
    """
    laag = SYSTEM_PROMPT.lower()
    assert "verzint er dus nooit één" in laag
    assert "voorgestelde jas-klassen" in laag


def test_prompt_eist_dat_een_citaat_letterlijk_is():
    """Aanhalingstekens beloven letterlijkheid, dus mag er niets in bewerkt zijn.

    Een antwoord op dev droeg zeven citaten die niet letterlijk in de bron stonden: weglatingen met
    (...), eigen samenvattingen tussen [ ] en vet middenin het citaat — met daarboven de zin dat
    alle citaten letterlijk waren. De groundingcontrole meldt dat achteraf; deze regel hoort te
    voorkomen dat het gebeurt.
    """
    laag = SYSTEM_PROMPT.lower()
    assert "letterlijk" in laag and "parafrase" in laag
    assert "aanhalingstekens" in laag
