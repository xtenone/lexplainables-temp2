"""De annotatie-flow in de supervisor-graaf: supervisor → OPHAAL-agent (retrieval) → aparte
ANNOTEER-stap. Draait de échte LangGraph (prod-config: decompositie aan) met FakeLLM/FakeGraph.

FakeLLM-volgorde per annotatie: supervisor(create) → ophaal-agent turn1(stream, tool_use) →
ophaal-agent turn2(stream, doel-JSON) → annoteer-stap(create, elementen-JSON) → critic-stap(create,
oordelen-JSON). De Critic mag falen zonder de annotatie te breken (elementen dan zonder aandacht).

De scenario's hieronder draaien met `critic_max_rondes=0`: dat is de keten ZONDER herzieningslus, en
tegelijk het bewijs dat die veiligheidsklep het oude gedrag exact reproduceert. De lus zelf staat in
`test_critic_lus.py`.
"""
from __future__ import annotations

import asyncio
import json

from agent.agent import answer_stream
from fakes import FakeGraph, FakeLLM, make_settings, response, text_block, tool_block

# get_lid/get_bepaling leveren SPARQL-TSV met ?tekst; JSON-string-encoded zoals de MCP.
LID_TSV = json.dumps('?nummer\t?tekst\t?jci\n"1"\t"De ontvanger verleent uitstel van betaling."@nl\t"jci"')

ELEMENTEN_JSON = json.dumps({
    "elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1", "toelichting": "wie", "alternatieven": []},
        {"klasse": "Rechtsbetrekking", "tekst": "verleent uitstel van betaling", "lid": "1", "toelichting": "wat", "alternatieven": []},
    ],
})

CRITIC_JSON = json.dumps({
    "oordelen": [
        {"index": 0, "aandacht": "groen", "motivatie": "helder"},
        {"index": 1, "aandacht": "rood", "motivatie": "twijfelachtige klasse"},
    ],
    "ontbrekend": [{"klasse": "Rechtsfeit", "reden": "de handeling zelf lijkt niet gemarkeerd"}],
})


def _run(gen):
    async def collect():
        return [ev async for ev in gen]

    return asyncio.run(collect())


def test_ophalen_dan_annoteren_grondt_lid():
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),        # supervisor
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW 1990"}')], "end_turn"),
        response([text_block(ELEMENTEN_JSON)], "end_turn"),                                           # annoteer-stap
        response([text_block(CRITIC_JSON)], "end_turn"),                                              # critic-stap
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))

    doel = next(e for e in events if e["type"] == "doel")["doel"]
    assert doel["bwbId"] == "BWBR0004770" and doel["artikel"] == "9" and doel["lid"] == "1"
    assert doel["leden_teksten"][0]["tekst"].startswith("De ontvanger")  # opgehaalde tekst meegestuurd

    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert {el["klasse"] for el in elementen} == {"Rechtssubject", "Rechtsbetrekking"}
    for el in elementen:
        assert el["grounded"] is True
        assert el["vindplaats"] == "BWBR0004770 art. 9 lid 1"

    # Critic-pas zette het aandacht-niveau per element.
    aandacht = {el["klasse"]: el["aandacht"] for el in elementen}
    assert aandacht == {"Rechtssubject": "groen", "Rechtsbetrekking": "rood"}
    # één ontbrekend-event met de vermoede klasse.
    ontbrekend = next(e for e in events if e["type"] == "ontbrekend")["items"]
    assert [o["klasse"] for o in ontbrekend] == ["Rechtsfeit"]


def test_get_bepaling_route_voor_decimaal_nummer():
    # Beleidsregel/divisie: de ophaal-agent gebruikt get_bepaling('9.1'); doel.nummer/artikel = '9.1'.
    bep_tsv = json.dumps('?nummer\t?tekst\t?label\n"9.1"\t"In de gevallen waarin voor voorlopige aanslagen."@nl\t"Afwijking"')
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer 9.1")], "end_turn"),                 # supervisor
        response([tool_block("t1", "get_bepaling", {"bwb_id": "BWBR0024096", "nummer": "9.1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0024096","nummer":"9.1","artikel":"","lid":"","citeertitel":"Leidraad Invordering 2008"}')], "end_turn"),
        response([text_block(json.dumps({"elementen": [{"klasse": "Rechtsfeit", "tekst": "voorlopige aanslagen", "lid": "", "toelichting": "x", "alternatieven": []}]}))], "end_turn"),
        response([text_block(json.dumps({"oordelen": [{"index": 0, "aandacht": "groen", "motivatie": "ok"}], "ontbrekend": []}))], "end_turn"),  # critic
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Leidraad Invordering 2008",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=bep_tsv),
    ))
    doel = next(e for e in events if e["type"] == "doel")["doel"]
    assert doel["nummer"] == "9.1" and doel["artikel"] == "9.1"
    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert len(elementen) == 1
    assert elementen[0]["vindplaats"] == "BWBR0024096 art. 9.1"


def test_alternatieven_maken_een_element_niet_geel():
    """Twijfel is geen aandachtspunt.

    Er stond een deterministische regel die alternatieven naar 'geel' bumpte. Gevolg: zo'n element
    kon nooit groen worden, en omdat de annoteerder juist wordt aangemoedigd om bij twijfel
    alternatieven te noemen, stond uiteindelijk álles "met aandacht" — waarmee die vlag betekenisloos
    werd. De Critic bepaalt nu de kleur; twijfel telt apart in de samenvatting.
    """
    elementen = json.dumps({"elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1", "toelichting": "wie",
         "alternatieven": [{"klasse": "Rechtsobject", "motivatie": "kan ook object zijn"}]},
    ]})
    critic = json.dumps({"oordelen": [{"index": 0, "aandacht": "groen", "motivatie": "leek ok"}], "ontbrekend": []})
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW"}')], "end_turn"),
        response([text_block(elementen)], "end_turn"),
        response([text_block(critic)], "end_turn"),
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    el = next(e["element"] for e in events if e["type"] == "element")
    assert el["aandacht"] == "groen", "het oordeel van de Critic blijft staan"
    assert el["alternatieven"][0]["klasse"] == "Rechtsobject", "de twijfel blijft wel zichtbaar"

    samenvatting = "".join(e["content"] for e in events if e["type"] == "token")
    assert "1 met twijfel" in samenvatting
    assert "met aandacht" not in samenvatting


def test_critic_faalt_stil_elementen_komen_door():
    # Geen critic-respons in de FakeLLM: de create() raist → critic degradeert, elementen komen door
    # met lege aandacht (de annotatie mag nooit breken).
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW"}')], "end_turn"),
        response([text_block(ELEMENTEN_JSON)], "end_turn"),
        # géén critic-respons → FakeLLM raist bij de critic-create
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert len(elementen) == 2
    assert all(el["aandacht"] == "" for el in elementen)   # gedegradeerd, maar wel doorgelaten


def test_annotatie_laat_leesbaar_spoor_in_geheugen(tmp_path):
    """Na een annotatie-beurt ziet een vervolgvraag (zelfde conversation_id) de gemarkeerde elementen
    terug in de historie — zodat 'waarom Rechtssubject?' context heeft."""
    settings = make_settings(enable_decomposition=False, checkpoint_db_path=str(tmp_path / "cp.db"))

    # Beurt 1: annoteer art. 9 lid 1.
    llm1 = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW"}')], "end_turn"),
        response([text_block(ELEMENTEN_JSON)], "end_turn"),
        response([text_block(CRITIC_JSON)], "end_turn"),
    ])
    _run(answer_stream("annoteer artikel 9 lid 1 IW", "annot-mem", settings=settings, llm=llm1, graph=FakeGraph(result=LID_TSV)))

    # Beurt 2: vervolgvraag; de agent moet de annotatie-samenvatting in de meegegeven historie zien.
    llm2 = FakeLLM([
        response([text_block("SPECIALIST: algemeen\nPLAN: direct")], "end_turn"),  # supervisor
        response([text_block("Omdat 'De ontvanger' de dragende actor is.")], "end_turn"),  # agent
    ])
    _run(answer_stream("waarom markeerde je 'De ontvanger' als Rechtssubject?", "annot-mem",
                       settings=settings, llm=llm2, graph=FakeGraph(result="")))

    serialized = " ".join(str(c.get("messages")) for c in llm2.calls)
    assert "[Annotatie" in serialized
    assert "Rechtssubject" in serialized and "De ontvanger" in serialized


def test_gewone_vraag_blijft_antwoord_geen_annotatie():
    llm = FakeLLM([
        response([text_block("SPECIALIST: algemeen\nPLAN: direct")], "end_turn"),  # supervisor → antwoord
        response([text_block("1. Wat is de termijn?")], "end_turn"),               # decompose (één regel)
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block("Zes weken (BWBR0004770 art. 9).")], "end_turn"),      # solve-antwoord
    ])
    events = _run(answer_stream(
        "wat is de betaaltermijn?", settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    assert not any(e["type"] in ("doel", "element") for e in events)
    tokens = "".join(e["content"] for e in events if e["type"] == "token")
    assert "Zes weken" in tokens


def test_elementen_dragen_een_stabiel_id_en_critic_koppelt_daarop():
    """Zonder id koppelt de Critic op positie, en dan landt een oordeel op het verkeerde element
    zodra een herzieningsronde iets toevoegt of weglaat. Dit is de basis onder die lus."""
    elementen = json.dumps({"elementen": [
        {"id": "el-aaa", "klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
        {"id": "el-bbb", "klasse": "Rechtsbetrekking", "tekst": "verleent uitstel van betaling", "lid": "1"},
    ]})
    # Bewust in omgekeerde volgorde: op positie zou dit de oordelen verwisselen.
    critic = json.dumps({"oordelen": [
        {"id": "el-bbb", "aandacht": "rood", "motivatie": "te grof", "actie": "vervang",
         "voorstel_klasse": "Rechtsfeit"},
        {"id": "el-aaa", "aandacht": "groen", "motivatie": "helder"},
    ], "ontbrekend": []})

    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1"}')], "end_turn"),
        response([text_block(elementen)], "end_turn"),
        response([text_block(critic)], "end_turn"),
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))

    els = {e["element"]["id"]: e["element"] for e in events if e["type"] == "element"}
    assert set(els) == {"el-aaa", "el-bbb"}, "de id's uit de annoteer-stap moeten doorstromen"
    assert els["el-aaa"]["aandacht"] == "groen"
    assert els["el-bbb"]["aandacht"] == "rood", "op id gekoppeld, niet op volgorde"


def test_verworpen_fragment_breekt_de_annotatie_niet():
    """Een citaat dat niet letterlijk in de tekst staat wordt verworpen; de rest komt gewoon door."""
    elementen = json.dumps({"elementen": [
        {"klasse": "Rechtssubject", "tekst": "De ontvanger", "lid": "1"},
        {"klasse": "Voorwaarde", "tekst": "een zin die nergens staat", "lid": "1"},
    ]})
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1"}')], "end_turn"),
        response([text_block(elementen)], "end_turn"),
        response([text_block(json.dumps({"oordelen": [], "ontbrekend": []}))], "end_turn"),
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0), llm=llm, graph=FakeGraph(result=LID_TSV),
    ))
    els = [e["element"] for e in events if e["type"] == "element"]
    assert [el["klasse"] for el in els] == ["Rechtssubject"]


def test_run_event_draagt_de_herkomst_van_de_beurt():
    """Precies één `run`-event, vóór de elementen, met het model dat ze maakte.

    Zonder deze herkomst kan de werkplek niet vastleggen waarmee geannoteerd is, en is achteraf
    niet meer te zeggen waar een markering vandaan komt.
    """
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW 1990"}')], "end_turn"),
        response([text_block(ELEMENTEN_JSON)], "end_turn"),
        response([text_block(CRITIC_JSON)], "end_turn"),
    ])
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0,
                               llm_model="claude-sonnet-4-6", agent_versie="9.9.9"),
        llm=llm, graph=FakeGraph(result=LID_TSV),
    ))

    runs = [e for e in events if e["type"] == "run"]
    assert len(runs) == 1
    run = runs[0]["run"]
    assert run["model"] == "claude-sonnet-4-6"
    assert run["provider"] == "anthropic_via_azure_foundry"
    assert run["agent_versie"] == "9.9.9"
    assert run["tijd"]

    soorten = [e["type"] for e in events]
    assert soorten.index("run") < soorten.index("element")



# --- Het corpus is de bepaling, niet de zoektocht ernaartoe -------------------------------------
#
# De ophaal-agent mag omwegen nemen (eerst het hele artikel, dan het lid). Het corpus waarop
# geannoteerd wordt hoort dát niet te weerspiegelen: het is precies de bepaling uit het doel,
# gericht opgehaald. Werd het uit de tool-trace gereconstrueerd, dan zat de tekst van álle
# opgehaalde leden erin — en dan keurt de brongetrouwheidscheck een fragment uit lid 2 goed als
# markering "in lid 1", mét de vindplaats van lid 1.

# Twee leden in één artikel-resultaat, zoals get_artikel dat teruggeeft.
ARTIKEL_TSV = json.dumps(
    "?tekst\t?jci\t?lid\t?lidnummer\t?lidtekst\n"
    '\t"jci"\t<urn:bwb:BWBR0004770:artikel:9:lid:1>\t"1"'
    '\t"Een belastingaanslag is invorderbaar zes weken na de dagtekening."\n'
    '\t"jci"\t<urn:bwb:BWBR0004770:artikel:9:lid:2>\t"2"'
    '\t"De ontvanger kan uitstel van betaling verlenen."'
)

TWEE_LEDEN_JSON = json.dumps({
    "elementen": [
        {"klasse": "Rechtsobject", "tekst": "Een belastingaanslag", "lid": "1",
         "toelichting": "waarover", "alternatieven": []},
        # Staat WEL in het artikel, maar niet in lid 1 — het lid dat geannoteerd wordt.
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel van betaling verlenen", "lid": "2",
         "toelichting": "wat", "alternatieven": []},
    ],
})


def test_corpus_blijft_binnen_het_gevraagde_lid():
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        # De ophaal-agent haalt het HELE artikel op — een normale omweg.
        response([tool_block("t1", "get_artikel", {"bwb_id": "BWBR0004770", "artikel": "9"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW 1990"}')], "end_turn"),
        response([text_block(TWEE_LEDEN_JSON)], "end_turn"),
        response([text_block(json.dumps({"oordelen": [], "ontbrekend": []}))], "end_turn"),
    ])
    graaf = FakeGraph(result=ARTIKEL_TSV)   # élke query levert beide leden; het lid-filter doet het werk
    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0),
        llm=llm, graph=graaf,
    ))

    corpus = next(e for e in events if e["type"] == "doel")["doel"]["leden_teksten"][0]["tekst"]
    assert "Een belastingaanslag" in corpus
    assert "uitstel van betaling" not in corpus, "lid 2 hoort niet in het corpus van lid 1"

    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert [el["tekst"] for el in elementen] == ["Een belastingaanslag"]
    assert elementen[0]["vindplaats"] == "BWBR0004770 art. 9 lid 1"


def test_corpus_valt_terug_op_de_trace_als_de_graaf_niets_geeft():
    """Geen corpus uit de graaf (onbekende vindplaats, andere structuur) mag de beurt niet slopen:
    dan is de tekst die de agent zag beter dan geen tekst."""
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","nummer":"","citeertitel":"IW 1990"}')], "end_turn"),
        response([text_block(ELEMENTEN_JSON)], "end_turn"),
        response([text_block(json.dumps({"oordelen": [], "ontbrekend": []}))], "end_turn"),
    ])

    def alleen_voor_de_toolcall(query: str) -> str:
        # get_artikel (de gerichte ophaal) levert niets; de lid-query van de agent wél.
        return "" if "/artikel/9>" in query else LID_TSV

    events = _run(answer_stream(
        "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        settings=make_settings(enable_decomposition=True, critic_max_rondes=0),
        llm=llm, graph=FakeGraph(results=alleen_voor_de_toolcall),
    ))

    elementen = [e["element"] for e in events if e["type"] == "element"]
    assert {el["klasse"] for el in elementen} == {"Rechtssubject", "Rechtsbetrekking"}
