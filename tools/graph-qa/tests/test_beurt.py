"""De beurt-driver: de uitkomst wordt vastgelegd zonder dat er een browser bij nodig is.

Dit is de tweede helft van "de beurt is van de server". Fase 1 zorgde dat de run doorloopt als de
kijker weggaat; hier wordt bewezen dat het resultaat dan ook echt ergens landt.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any

import pytest

from agent.beurt import BeurtSchrijver, voer_beurt_uit
from agent.runs import Run
from agent.wetsanalyse_api import GesprekVerdwenen, WetsanalyseApiFout
from tests.fakes import make_settings


def asyncio_test(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        return asyncio.run(fn(*args, **kwargs))
    return wrapper


class NepApi:
    """Legt vast wát er geschreven zou worden, zonder netwerk."""

    def __init__(self, *, faalt: bool | str = False) -> None:
        self.faalt = faalt
        self.documenten: list[dict[str, Any]] = []
        self.element_puts: list[dict[str, Any]] = []
        self.berichten: list[tuple[str, dict[str, Any]]] = []
        self.gesloten = False
        self.verworpen = 0

    async def maak_document(self, **kw: Any) -> str:
        self.documenten.append(kw)
        return "slug-1"

    async def zet_elementen(self, slug: str, **kw: Any) -> dict[str, Any]:
        if self.faalt == "elementen":
            raise WetsanalyseApiFout("PUT /v1/annotatie/documenten/…/elementen → 422", 422)
        self.element_puts.append({"slug": slug, **kw})
        return {}

    async def voeg_bericht_toe(self, gesprek_id: str, bericht: dict[str, Any]) -> dict[str, Any]:
        if self.faalt == "verdwenen":
            raise GesprekVerdwenen("POST /v1/gesprekken/… → 404", 404)
        if self.faalt:
            raise WetsanalyseApiFout("POST /v1/gesprekken/… → 503")
        self.berichten.append((gesprek_id, bericht))
        return {}

    async def aclose(self) -> None:
        self.gesloten = True


@pytest.fixture
def api(monkeypatch):
    nep = NepApi()
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)
    return nep


def _settings():
    return make_settings(wetsanalyse_api_url="http://api:3000", wetsanalyse_api_token="t", qa_api_token="q")


def _run(stop: bool = False) -> Run:
    run = Run(run_id="run-1", conversation_id="g1", vraag="v")
    run.stop_gevraagd = stop
    return run


async def _draai(events, *, settings=None, run=None, gesprek_id="g1", user_id="jurist"):
    async def stroom():
        for e in events:
            yield e

    return [
        ev async for ev in voer_beurt_uit(
            stroom(), settings=settings or _settings(), run=run or _run(),
            gesprek_id=gesprek_id, user_id=user_id,
        )
    ]


@asyncio_test
async def test_antwoordbeurt_wordt_vastgelegd(api):
    uit = await _draai([
        {"type": "status", "message": "Graaf bevragen"},
        {"type": "token", "content": "Het "},
        {"type": "token", "content": "antwoord."},
        {"type": "sources", "sources": [{"label": "IW art. 9", "uri": "x"}]},
        {"type": "done"},
    ])

    gesprek_id, bericht = api.berichten[0]
    assert gesprek_id == "g1"
    assert bericht["tekst"] == "Het antwoord."
    assert bericht["bronnen"] == [{"label": "IW art. 9", "uri": "x"}]
    assert bericht["denk"] == "· Graaf bevragen"
    # De sleutel die dubbel wegschrijven voorkomt als er twee tabbladen meekijken.
    assert bericht["run_id"] == "run-1"
    assert api.gesloten
    # `done` gaat er pas uit ná het wegschrijven: anders ziet een client die precies dan herlaadt
    # noch de run, noch het bericht.
    assert [e["type"] for e in uit][-2:] == ["opgeslagen", "done"]


@asyncio_test
async def test_annotatiebeurt_maakt_document_en_elementen(api):
    doel = {"bwbId": "BWBR0004770", "artikel": "9", "lid": "1", "citeertitel": "Invorderingswet 1990"}
    uit = await _draai([
        {"type": "doel", "doel": doel},
        {"type": "run", "run": {"model": "claude", "provider": "azure"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "de ontvanger"}},
        {"type": "suggestie", "suggestie": {"element_id": "m1", "aandacht": "geel", "motivatie": "let op"}},
        {"type": "ontbrekend", "items": [{"klasse": "Rechtsfeit"}]},
        {"type": "done"},
    ])

    assert api.documenten == [{
        "bwb_id": "BWBR0004770", "artikel": "9", "lid": "1", "citeertitel": "Invorderingswet 1990",
    }]
    put = api.element_puts[0]
    assert put["slug"] == "slug-1"
    assert put["elementen"][0]["tekst"] == "de ontvanger"
    assert put["suggesties"][0]["aandacht"] == "geel"
    assert put["run"] == {"model": "claude", "provider": "azure"}

    _, bericht = api.berichten[0]
    assert bericht["annotatie_slug"] == "slug-1"
    # Het label reist mee zodat de kaart zichzelf kan benoemen als het document later weg is.
    assert bericht["annotatie_titel"] == "Invorderingswet 1990 — art. 9 lid 1"
    assert bericht["ontbrekend"] == [{"klasse": "Rechtsfeit"}]

    opgeslagen = [e for e in uit if e["type"] == "opgeslagen"][0]
    assert opgeslagen["annotatie_slug"] == "slug-1"


@asyncio_test
async def test_een_element_zonder_eindoordeel_breekt_de_hele_annotatie_niet(api):
    """`Aandacht` kent alleen groen/geel/rood; een lege string is geen oordeel maar 422.

    Op dev liep daar een complete annotatie op stuk: de agent was klaar en gegrond, de PUT gaf 422 op
    één element zonder eindoordeel, en de jurist hield een leeg document over. Alles-of-niets bij het
    wegschrijven betekent dat het zwakste element de rest meesleurt.
    """
    doel = {"bwbId": "BWBR0004770", "artikel": "9", "lid": "1", "citeertitel": "Invorderingswet 1990"}
    await _draai([
        {"type": "doel", "doel": doel},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "de ontvanger",
                                        "aandacht": ""}},
        {"type": "element", "element": {"id": "e2", "klasse": "Voorwaarde", "tekst": "indien",
                                        "aandacht": "geel"}},
        {"type": "done"},
    ])

    from agent.wetsanalyse_api import naar_contract

    elementen = api.element_puts[0]["elementen"]
    assert naar_contract(elementen[0])["aandacht"] is None, "geen oordeel is None, geen lege string"
    assert naar_contract(elementen[1])["aandacht"] == "geel", "een echt oordeel blijft staan"


@asyncio_test
async def test_zonder_elementen_geen_leeg_document(api):
    """`emit_node` is terminaal: een beurt die eerder eindigt heeft nul elementen. Zou het document
    al bij het `doel`-event ontstaan, dan bleef elk afgebroken pad als leeg skelet in de
    werkvoorraad van de jurist staan."""
    await _draai([
        {"type": "doel", "doel": {"bwbId": "BWBR0004770", "artikel": "9"}},
        {"type": "token", "content": "Ik vond geen JAS-elementen."},
        {"type": "done"},
    ])
    assert api.documenten == []
    _, bericht = api.berichten[0]
    assert bericht["tekst"] == "Ik vond geen JAS-elementen."


@asyncio_test
async def test_mislukte_elementen_beloven_geen_bewaarde_annotatie(monkeypatch):
    """Het document bestaat dan wel, de markeringen niet — dat is iets anders dan "bewaard".

    Op dev liep een run hierop stuk (422 op de PUT) en las de jurist dat de annotatie bewaard was en
    dat opnieuw proberen een tweede zou opleveren. Er viel niets terug te vinden: het document was
    leeg. Een melding die het werk veiliger voorstelt dan het is, is erger dan geen melding.
    """
    nep = NepApi(faalt="elementen")
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)
    uit = await _draai([
        {"type": "doel", "doel": {"bwbId": "B", "artikel": "9", "citeertitel": "Wet"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "t"}},
        {"type": "done"},
    ])

    fout = [e for e in uit if e["type"] == "error"][0]
    assert "leeg document" in fout["message"]
    assert "opnieuw" in fout["message"], "hier is opnieuw proberen juist wél het advies"
    assert "bewaard" not in fout["message"]


@asyncio_test
async def test_verworpen_markeringen_worden_gemeld(monkeypatch):
    """De api laat een kapot element vallen in plaats van de ronde te weigeren — dat maakt een luide
    fout stil. Zonder deze melding ziet de jurist dertien markeringen zonder te weten dat het er
    vijftien hadden moeten zijn."""
    nep = NepApi()
    nep.verworpen = 2
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)
    uit = await _draai([
        {"type": "doel", "doel": {"bwbId": "B", "artikel": "9", "citeertitel": "Wet"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "t"}},
        {"type": "done"},
    ])

    waarschuwing = [e for e in uit if e["type"] == "waarschuwing"][0]
    assert "2 markeringen" in waarschuwing["message"]
    assert not [e for e in uit if e["type"] == "error"], "de beurt is geslaagd, dit is geen fout"
    assert [e for e in uit if e["type"] == "opgeslagen"], "en wat er wél is, is opgeslagen"


@asyncio_test
async def test_zonder_verworpen_geen_waarschuwing(api):
    uit = await _draai([
        {"type": "doel", "doel": {"bwbId": "B", "artikel": "9", "citeertitel": "Wet"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "t"}},
        {"type": "done"},
    ])
    assert not [e for e in uit if e["type"] == "waarschuwing"]


@asyncio_test
async def test_element_wordt_ontdubbeld(api):
    """De annoteerder ⇄ Critic-lus kan hetzelfde element opnieuw sturen; de laatste versie wint."""
    doel = {"bwbId": "B", "artikel": "9", "citeertitel": "Wet"}
    await _draai([
        {"type": "doel", "doel": doel},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "t"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtsobject", "tekst": "t"}},
        {"type": "done"},
    ])
    elementen = api.element_puts[0]["elementen"]
    assert len(elementen) == 1
    assert elementen[0]["klasse"] == "Rechtsobject"


@asyncio_test
async def test_stoppen_bewaart_wat_er_al_stond(api):
    """Weggooien wat de agent al schreef is niet wat 'stoppen' betekent."""
    uit = await _draai(
        [
            {"type": "token", "content": "Half "},
            {"type": "token", "content": "afgemaakt."},
            {"type": "done"},
        ],
        run=_run(stop=True),
    )
    _, bericht = api.berichten[0]
    assert bericht["tekst"] == "Half afgemaakt.\n\n_(gestopt)_"
    assert uit[-1]["type"] == "done"


@asyncio_test
async def test_stoppen_vóór_de_voorstellen_belooft_niets(api):
    """`emit_node` is terminaal: stoppen daarvóór levert écht nul voorstellen op. Dan is "er waren
    nog geen voorstellen" het eerlijke antwoord, niet een leeg bericht of een half document."""
    await _draai(
        [{"type": "status", "message": "Ophalen"}, {"type": "done"}],
        run=_run(stop=True),
    )
    _, bericht = api.berichten[0]
    assert bericht["tekst"] == "_Gestopt — er waren nog geen voorstellen._"
    assert api.documenten == []


@asyncio_test
async def test_zonder_api_blijft_het_een_doorgeefluik(api):
    """Geen api geconfigureerd → de werkplek schrijft weg, zoals vroeger. Lokaal draaien zonder api
    moet mogelijk blijven."""
    uit = await _draai(
        [{"type": "token", "content": "x"}, {"type": "done"}],
        settings=make_settings(),
    )
    assert api.berichten == []
    assert [e["type"] for e in uit] == ["token", "done"]


@asyncio_test
async def test_zonder_gebruiker_wordt_er_niets_geschreven(api):
    """De api scopet per gebruiker; zonder identiteit is er niemand om namens te handelen."""
    await _draai([{"type": "token", "content": "x"}, {"type": "done"}], user_id="")
    assert api.berichten == []


@asyncio_test
async def test_schrijffout_wordt_zichtbaar(monkeypatch):
    """Stil verliezen is het ergste wat hier kan gebeuren: dan ontdekt de jurist pas later dat het
    gesprek een gat heeft."""
    nep = NepApi(faalt=True)
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)
    uit = await _draai([{"type": "token", "content": "x"}, {"type": "done"}])
    fouten = [e for e in uit if e["type"] == "error"]
    assert fouten and "niet opgeslagen" in fouten[0]["message"]
    assert uit[-1]["type"] == "done"
    assert nep.gesloten


@asyncio_test
async def test_half_vastgelegde_annotatie_zegt_wat_er_wel_staat(monkeypatch):
    """Document en elementen staan er al, alleen het chatbericht niet.

    "Probeer de vraag opnieuw" is dan een slecht advies: dat draait 60-90 seconden annoteren over en
    levert een tweede document op. De melding hoort te zeggen wat er wél bewaard is.
    """
    nep = NepApi(faalt=True)
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)

    uit = await _draai([
        {"type": "doel", "doel": {"bwbId": "BWBR0004770", "artikel": "9", "lid": "1"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "De ontvanger"}},
        {"type": "done"},
    ])

    fout = next(e for e in uit if e["type"] == "error")
    assert "annotatie is bewaard" in fout["message"].lower()
    assert fout["annotatie_slug"] == "slug-1", "zodat de client er meteen heen kan wijzen"
    assert "opnieuw" not in fout["message"] or "tweede annotatie" in fout["message"]
    # Het document en de elementen zijn wél geschreven — dat is precies waarom de melding anders is.
    assert nep.documenten and nep.element_puts


def test_schrijver_houdt_denkproces_en_tekst_gescheiden():
    """Narratie is geen antwoord: `status`/`reason` vormen het denkproces, `token` het antwoord."""
    schrijver = BeurtSchrijver()
    for event in [
        {"type": "status", "message": "Stap één"},
        {"type": "reason", "content": "ik denk na"},
        {"type": "token", "content": "Antwoord"},
    ]:
        schrijver.verwerk(event)
    assert schrijver.tekst == "Antwoord"
    assert schrijver.denk == "· Stap éénik denk na"


@asyncio_test
async def test_verwijderd_gesprek_is_geen_storing(monkeypatch):
    """Live gevonden op dev: de jurist verwijderde het gesprek terwijl de beurt liep, en kreeg
    vervolgens een foutmelding over zijn eigen handeling.

    De api weigert terecht (erin schrijven zou een verwijderd gesprek half laten herrijzen), maar
    dat is geen storing om alarm over te slaan — dat leert mensen meldingen negeren. Het
    annotatiedocument blijft wél bestaan: annotaties staan los van hun gesprek.
    """
    nep = NepApi(faalt="verdwenen")
    monkeypatch.setattr("agent.beurt.WetsanalyseApi", lambda *_a, **_k: nep)

    uit = await _draai([
        {"type": "doel", "doel": {"bwbId": "B", "artikel": "9", "citeertitel": "Wet"}},
        {"type": "element", "element": {"id": "e1", "klasse": "Rechtssubject", "tekst": "t"}},
        {"type": "done"},
    ])

    assert [e for e in uit if e["type"] == "error"] == []   # geen alarm
    assert uit[-1]["type"] == "done"                        # de beurt eindigt gewoon
    assert nep.documenten and nep.element_puts               # het werk is bewaard
    assert nep.gesloten
