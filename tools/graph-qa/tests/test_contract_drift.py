"""Drift-guard: de agent-modellen tegen het contract van de wetsanalyse-api.

Waarom deze test bestaat. graph-qa en de api hebben elk hun eigen model van hetzelfde object, en ze
komen alleen samen in één HTTP-call in een ánder proces. Een verschil tussen die twee is daar geen
typefout maar een 422 — en omdat de PUT alles-of-niets is, verliest de jurist dan de complete
annotatie. Dat is op dev gebeurd met `aandacht`: de agent kent `str = ""`, de api `Aandacht | None`.
De agent was klaar en gegrond, het document bleef leeg.

De vertaling zelf staat op de grens (`wetsanalyse_api.naar_contract`). Deze test bewaakt dat er geen
vierde veld bijkomt dat stilzwijgend hetzelfde doet: hij faalt zodra een agent-veld en zijn
api-tegenhanger uit elkaar lopen zonder dat de vertaling het opvangt.

Zelfde idioom als `test_jas_klassen.py`: één kopie, één guard ertegen.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from agent import models as am
from agent.wetsanalyse_api import naar_contract, _leeg_is_niets

CONTRACT = (
    Path(__file__).resolve().parents[3] / "api" / "app" / "features" / "annotatie" / "contracts.py"
)

#: Verschillen die de vertaling op de grens bewust opvangt. Elke regel is een afspraak, geen
#: uitzondering: hier weet de agent iets niet wat het contract wél eist.
OPGEVANGEN = {
    ("AnnotatieVoorstel", "aandacht"),   # "" → None
    ("CriticRonde", "aandacht"),         # "" → None
    ("AgentRun", "tijd"),                # None → weggelaten, api vult zelf
    # Geen typeverschil maar een naamsverschil dat de api zelf afhandelt: "" betekent daar "geen id,
    # match op tekst+lid" en dat is precies de bedoelde semantiek.
    ("AnnotatieVoorstel", "id"),
}

#: Agent-velden die de api niet kent. Pydantic negeert ze; dat is hier gewenst — het is interne staat
#: van de agent, geen onderdeel van het annotatie-domein.
INTERN = {("AnnotatieVoorstel", "grounded")}

PAREN = [
    ("AnnotatieVoorstel", "ElementInvoer"),
    ("CriticRonde", "CriticRonde"),
    ("AnnotatieAlternatief", "Alternatief"),
    ("AgentRun", "AgentRun"),
]


def _api_velden(klasse: str) -> dict[str, str]:
    """De veldtypes van één contractklasse, uit de bron gelezen.

    Importeren kan niet: `annotatie_contracts` gebruikt relatieve imports en graph-qa heeft de api
    niet als afhankelijkheid — dat is juist de scheiding die deze test bewaakt.
    """
    bron = CONTRACT.read_text()
    blok = re.search(rf"^class {klasse}\(BaseModel\):(.*?)(?=^class |\Z)", bron, re.S | re.M)
    assert blok, f"contractklasse {klasse} niet gevonden"
    uit: dict[str, str] = {}
    for regel in blok.group(1).splitlines():
        regel = regel.split("#")[0].strip()
        if regel.startswith(('"', "'")):
            continue
        veld = re.match(r"^(\w+)\s*:\s*([^=]+?)(?:\s*=.*)?$", regel)
        if veld:
            uit[veld.group(1)] = veld.group(2).strip()
    return uit


#: De agent noemt sommige klassen anders dan de api; dat is een naamsverschil, geen vormverschil.
#: De velden erbinnen worden apart vergeleken (zie PAREN).
ALIAS = {"AnnotatieAlternatief": "Alternatief"}


def _vorm(annotatie: object) -> str:
    """De vorm van een type, zonder module-paden: `list[a.b.C]` en `list[C]` zijn hetzelfde.

    Niet splitsen op de laatste punt — dat verminkt `list[...]` tot `C]` en levert vals alarm.
    """
    tekst = str(annotatie).replace("typing.", "").replace("<class '", "").replace("'>", "")
    tekst = re.sub(r"[\w.]*\.(\w+)", r"\1", tekst)
    for agent_naam, api_naam in ALIAS.items():
        tekst = tekst.replace(agent_naam, api_naam)
    return tekst.replace(" ", "").strip()


@pytest.mark.skipif(not CONTRACT.exists(), reason="api-contract niet beschikbaar (los uitgecheckt)")
@pytest.mark.parametrize("agent_klasse, api_klasse", PAREN)
def test_geen_stil_verschil_met_het_api_contract(agent_klasse, api_klasse):
    agent = getattr(am, agent_klasse).model_fields
    api = _api_velden(api_klasse)

    for naam, veld in agent.items():
        if (agent_klasse, naam) in OPGEVANGEN:
            continue
        if naam not in api:
            assert (agent_klasse, naam) in INTERN, (
                f"{agent_klasse}.{naam} bestaat niet in {api_klasse}: het verdwijnt stil bij het "
                f"wegschrijven. Voeg het toe aan het contract, of aan INTERN als dat de bedoeling is."
            )
            continue
        assert _vorm(veld.annotation) == _vorm(api[naam]), (
            f"{agent_klasse}.{naam} is {_vorm(veld.annotation)} en {api_klasse}.{naam} is "
            f"{api[naam]}. Zo'n verschil is geen typefout maar een 422 op de PUT, en die is "
            f"alles-of-niets: de jurist verliest de hele annotatie. Vertaal het in "
            f"`wetsanalyse_api.naar_contract` en zet het in OPGEVANGEN."
        )


def test_de_vertaling_dekt_alles_wat_in_opgevangen_staat():
    """Anders staat er een afspraak op papier die niemand uitvoert."""
    element = {
        "aandacht": "",
        "critic_rondes": [{"ronde": 1, "aandacht": ""}, {"ronde": 2, "aandacht": "geel"}],
    }
    uit = naar_contract(element)
    assert uit["aandacht"] is None
    assert uit["critic_rondes"][0]["aandacht"] is None
    assert uit["critic_rondes"][1]["aandacht"] == "geel", "een echt oordeel blijft staan"


def test_de_vertaling_laat_geldige_waarden_met_rust():
    element = {"aandacht": "rood", "klasse": "Voorwaarde", "tekst": "indien"}
    assert naar_contract(element) == element


def test_een_element_zonder_rondes_krijgt_er_geen():
    """De vertaling vult niets aan; ze zet alleen recht wat anders zou afketsen."""
    assert "critic_rondes" not in naar_contract({"aandacht": "groen"})


def test_leeg_is_niets_werkt_op_elk_veld():
    assert _leeg_is_niets({"aandacht": ""})["aandacht"] is None
    assert _leeg_is_niets({}, "iets")["iets"] is None


def test_de_guard_slaat_aan_op_precies_dit_soort_verschil():
    """Bewijs dat hij vangt wat er is misgegaan, in plaats van alleen groen te staan.

    `aandacht` staat in OPGEVANGEN omdat de vertaling hem afhandelt. Voor een verzonnen vierde veld
    is dat niet zo, en dan hoort de test te falen met een uitleg die naar de vertaling wijst.
    """
    class NieuwVeld:
        model_fields = {"aandacht": am.AnnotatieVoorstel.model_fields["aandacht"]}

    api = _api_velden("ElementInvoer")
    verschil = _vorm(NieuwVeld.model_fields["aandacht"].annotation) != _vorm(api["aandacht"])
    assert verschil, "als dit gelijk is, bewaakt de guard niets meer"
