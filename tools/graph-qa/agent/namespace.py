"""
De IRI-ruimte van de kennisgraaf — één bron van waarheid binnen graph-qa.

Waarom deze module bestaat. De basis-IRI wordt door de **importer** bepaald
(`tools/bwb-import/app/rdf_vocab.py`), maar hij werd hier op drie plekken los
overgetypt: als SPARQL-prefix, als filterwaarde en als regex in de
provenance-herkenning. Drie kopieën van dezelfde string die niets van elkaar
weten, is drie kansen om stil uit elkaar te lopen — en het gevolg is niet een
foutmelding maar een leeg antwoord: de filters matchen dan simpelweg niets.

De waarde is een eigenschap van de **data in de graaf**, niet van een sessie.
Ze komt daarom uit de omgeving (dezelfde variabelen als de importer gebruikt) en
wordt bij import vastgelegd, niet per vraag opnieuw bepaald.

De drift-guard `tests/test_namespace_drift.py` bewaakt dat deze waarden gelijk
blijven aan die van de importer en de frontend.
"""
from __future__ import annotations

import os
import re

#: Documentruimte: de IRI's van regelingen, artikelen en leden.
BASIS = os.getenv("GRAPHDB_BASE_IRI") or "urn:bwb:"

#: Vocabulaireruimte: de predicaten en klassen. Bewust géén vindplaatsen — zie provenance.
ONTOLOGIE = os.getenv("GRAPHDB_ONTOLOGY_IRI") or "urn:bwb-ns:"


#: Scheidingsteken tussen segmenten: ``:`` in een URN-ruimte, ``/`` in een http-IRI.
#: Spiegelt ``Vocab._sep`` in tools/bwb-import/app/rdf_vocab.py.
SEP = ":" if BASIS.startswith("urn:") else "/"


def vindplaats_patroon(basis: str = BASIS) -> str:
    """Regex-patroon dat een vindplaats-IRI in vrije tekst herkent.

    Bij een http(s)-basis blijven beide schema's toegestaan: een model of een
    tool-antwoord dat `http://` teruggeeft waar de graaf `https://` voert, wijst
    nog steeds dezelfde bron aan en mag niet als niet-onderbouwd wegvallen.
    """
    if basis.startswith("https://"):
        kern = re.escape(basis[len("https://") :])
        return r"https?://" + kern + r"[^\s\"'<>)\]}\\]+"
    return re.escape(basis) + r"[^\s\"'<>)\]}\\]+"
