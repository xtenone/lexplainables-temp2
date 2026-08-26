"""Afkortingen van veelgebruikte wetten -> BWB-id, voor tekstuele verwijzingen.

Bewust klein en expliciet (geen poging tot volledigheid): alleen afkortingen
die in de praktijk in wetteksten en beleidsregels voorkomen. Het Burgerlijk
Wetboek is per boek een eigen regeling; het boeknummer zit in het
artikelnummer ("6:162" -> Boek 6).
"""

from __future__ import annotations

# Afkorting -> BWB-id.
AFKORTING_BWB: dict[str, str] = {
    "Awb": "BWBR0005537",  # Algemene wet bestuursrecht
    "AWR": "BWBR0002320",  # Algemene wet inzake rijksbelastingen
    "Awr": "BWBR0002320",
    "IW": "BWBR0004770",  # Invorderingswet 1990
    "Sr": "BWBR0001854",  # Wetboek van Strafrecht
    "Sv": "BWBR0001903",  # Wetboek van Strafvordering
    "Rv": "BWBR0001827",  # Wetboek van Burgerlijke Rechtsvordering
    "Fw": "BWBR0001860",  # Faillissementswet
    "Awir": "BWBR0018472",  # Algemene wet inkomensafhankelijke regelingen
    "Gw": "BWBR0001840",  # Grondwet
}

# Burgerlijk Wetboek: boeknummer (prefix van het artikelnummer) -> BWB-id.
_BW_BOEKEN: dict[str, str] = {
    "1": "BWBR0002656",
    "2": "BWBR0003045",
    "3": "BWBR0005291",
    "4": "BWBR0002761",
    "5": "BWBR0005288",
    "6": "BWBR0005289",
    "7": "BWBR0005290",
    "8": "BWBR0005034",
    "10": "BWBR0030068",
}


def zoek_bwb_id(afkorting: str, artikelnummer: str) -> str | None:
    """BWB-id bij een wetafkorting; ``None`` als de afkorting onbekend is.

    Voor "BW" bepaalt het boeknummer in het artikelnummer ("6:162" -> Boek 6)
    welke regeling bedoeld is.
    """
    if afkorting == "BW":
        boek, sep, _ = artikelnummer.partition(":")
        return _BW_BOEKEN.get(boek) if sep else None
    return AFKORTING_BWB.get(afkorting)
