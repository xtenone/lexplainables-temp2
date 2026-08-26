"""
Specialisten voor het supervisor-patroon (multi-agent).

Een specialist is een **declaratieve config**: een focus-prompt bovenop SYSTEM_PROMPT +
een toegestane tool-subset. De router (agent/orchestrator.py) kiest er één per vraag; de
agent-node draait daarna de gewone agent↔tools-lus met die config. Zo delen alle
specialisten dezelfde tool-laag, grounding en geheugen — het verschil zit in gedrag en
tool-bereik. Uitbreiden = een entry toevoegen (bv. later een regelspraak-specialist).
"""
from __future__ import annotations

from dataclasses import dataclass

from .annotatie_prompt import annotatie_systeemprompt


@dataclass(frozen=True)
class Specialist:
    system: str
    tools: frozenset[str] | None  # None = alle tools


# De OPHAAL-agent: vindt en haalt de EXACTE bepaling op die geannoteerd moet worden. Geen annotatie —
# alleen retrieval + een doel-JSON. Overschrijft bewust de QA-antwoordinstructies uit SYSTEM_PROMPT.
_RETRIEVAL_SYSTEM = (
    "LET OP — je BEANTWOORDT deze vraag niet en je annoteert niet. Je enige taak is de EXACTE wettelijke "
    "bepaling OPHALEN die de gebruiker wil laten annoteren, zodat een volgende stap die kan analyseren.\n"
    "WERKWIJZE:\n"
    "- Bepaal om welke regeling + bepaling het gaat. Ken je de bwbId nog niet, zoek die met "
    "search_wetgeving/semantic_search.\n"
    "- Haal de tekst van precies die bepaling op:\n"
    "  • gewone wet met leden en een lid is genoemd → get_lid(bwb_id, artikel, lid);\n"
    "  • heel artikel → get_artikel(bwb_id, artikel);\n"
    "  • beleidsregel/circulaire of een DECIMAAL nummer zoals '9.1' (bv. de Leidraad Invordering 2008), "
    "of als get_lid/get_artikel niets geven → get_bepaling(bwb_id, nummer) met dat nummer "
    "(bv. '9.1', '22a'). Let op: 'artikel 9 lid 1' van een beleidsregel bedoelt vaak bepaling '9.1'.\n"
    "- Je MOET eindigen met een geslaagde get_lid/get_artikel/get_bepaling-call die de tekst teruggaf.\n"
    "Geef daarna UITSLUITEND deze JSON terug (geen proza):\n"
    '{"bwbId": "<BWBR…>", "nummer": "<het opgehaalde nummer, bv. 9.1>", "artikel": "<artikelnr of leeg>", '
    '"lid": "<lidnummer of leeg>", "citeertitel": "<naam van de regeling>"}\n'
    "\n"
    "UITZONDERING — de gebruiker noemt GEEN bepaling maar een ONDERWERP ('alles over aansprakelijkheid "
    "van de bestuurder', 'de bepalingen over uitstel van betaling'). Kies er dan NIET zelf één uit: "
    "zoek met semantic_search/search_wetgeving en leg de gevonden bepalingen als keuze voor. Haal in "
    "dat geval GEEN tekst op en geef deze JSON terug:\n"
    '{"kandidaten": [{"bwbId": "<BWBR…>", "artikel": "<nr>", "lid": "<nr of leeg>", '
    '"citeertitel": "<regeling>", "fragment": "<eerste zin van de bepaling>"}]}\n'
    "Maximaal 8 kandidaten, de meest relevante eerst. Twijfel je of het een onderwerp of een concrete "
    "bepaling is, en wijst de vraag één bepaling aan? Dan is het een concrete bepaling — haal die op."
)


SPECIALISTS: dict[str, Specialist] = {
    "definitie": Specialist(
        system=(
            "Je bent de DEFINITIE-specialist. Je herleidt en verklaart juridische begrippen. "
            "Begin bij resolve_begrip en de definitieartikelen; citeer de brondefinitie letterlijk "
            "met vindplaats en benoem of het een wettelijke definitie of interpretatie is.\n"
            "Begripsbepalingen staan doorgaans in artikel 1 of 2 van een regeling; haal die beide "
            "in één beurt op in plaats van na elkaar. Het definitie-artikel zelf bevat vaak alleen "
            "de aanhef ('Deze wet verstaat onder:') — de definities zitten in de onderdelen van het "
            "lid, die get_lid meelevert. Citeer de vindplaats van het ONDERDEEL (…&o=k), niet die "
            "van het hele lid."
        ),
        tools=frozenset({
            "resolve_begrip", "search_wetgeving", "semantic_search",
            "get_artikel", "get_lid", "graph_schema", "raw_sparql",
        }),
    ),
    "duiding": Specialist(
        system=(
            "Je bent de DUIDINGS-specialist. Je legt de betekenis, structuur en samenhang van een "
            "bepaling uit. Gebruik get_context voor de bepaling met haar structuur en verwijzingen, "
            "en follow_verwijzingen/referenced_by om kruisverwijzingen te volgen."
        ),
        tools=frozenset({
            "get_context", "get_artikel", "get_lid", "follow_verwijzingen", "referenced_by",
            "search_wetgeving", "semantic_search", "graph_schema", "raw_sparql",
        }),
    ),
    "algemeen": Specialist(system="", tools=None),
    # De OPHAAL-agent voor de annotatie-flow: dezelfde volledige retrieval-kist als Lex + get_bepaling,
    # zodat hij de EXACTE bepaling vindt (ook beleidsregels/circulaires met decimale nummers zoals "9.1").
    # Hij annoteert NIET; hij levert alleen het doel (JSON). De annoteer-stap doet daarna de JAS-analyse.
    "retrieval": Specialist(
        system=_RETRIEVAL_SYSTEM,
        tools=frozenset({
            "search_wetgeving", "semantic_search", "get_context", "get_artikel", "get_lid",
            "get_bepaling", "get_regeling_info", "resolve_begrip", "follow_verwijzingen",
        }),
    ),
}

DEFAULT = "algemeen"


def get(name: str | None) -> Specialist:
    """Specialist op naam; valt terug op 'algemeen' bij onbekend/leeg."""
    return SPECIALISTS.get((name or "").strip().lower(), SPECIALISTS[DEFAULT])
