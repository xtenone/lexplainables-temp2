"""Annotatie-domein (api): document-lifecycle, human-decisions, append-only audit, client-scoping."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

BASIS = "/v1/annotatie/documenten"


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("WETSANALYSE_AUTH_REQUIRED", "0")

    from app import db, ratelimit
    from app.annotatie_contracts import AnnotatieDocument
    from app.annotatie_store import AnnotatieStore
    from app.config import get_settings
    from app.deps import get_annotatie_store
    from conftest import maak_testgebruikers

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    ratelimit.reset()

    db.init_engine("sqlite+aiosqlite://")
    await db.create_all()
    await maak_testgebruikers("gebruiker-a", "gebruiker-b")

    # Document van een andere GEBRUIKER — moet voor "gebruiker-a" onzichtbaar zijn (404).
    await AnnotatieStore().maak_document(
        AnnotatieDocument(slug="andermans-doc", user_id="gebruiker-b", client_id="andere-client",
                          bwbId="BWBR3", artikel="1")
    )

    from app.main import app
    # De BFF zet de ingelogde identiteit als vertrouwde X-User-Id-header; hier "gebruiker-a".
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers={"X-User-Id": "gebruiker-a"}
    ) as ac:
        yield ac

    get_settings.cache_clear()
    get_annotatie_store.cache_clear()
    await db.dispose_engine()


async def _maak_doc(client) -> str:
    r = await client.post(BASIS, json={"bwbId": "BWBR0004770", "artikel": "9", "werkgebied": "invordering"})
    assert r.status_code == 201
    return r.json()["slug"]


async def test_document_lifecycle_en_audit(client):
    slug = await _maak_doc(client)

    # verschijnt in de eigen lijst
    lijst = (await client.get(BASIS)).json()
    assert any(d["slug"] == slug for d in lijst)

    # voorgestelde elementen: 2 geldig + 1 ongeldige klasse (verworpen)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"},
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel verlenen", "lid": "1"},
        {"klasse": "OnzinKlasse", "tekst": "iets", "lid": "1"},
    ]})
    assert r.status_code == 200
    doc = r.json()
    assert len(doc["elementen"]) == 2
    assert all(e["lifecycle"] == "voorgesteld" and e["herkomst"] == "agent" for e in doc["elementen"])
    el0, el1 = doc["elementen"][0]["id"], doc["elementen"][1]["id"]

    # approve
    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el0}/beslissing", json={"type": "approve"})).json()
    assert next(e for e in doc["elementen"] if e["id"] == el0)["lifecycle"] == "human_approved"

    # edit zonder review_reason → mag, de server leidt de reden af uit de diff.
    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el1}/beslissing",
                             json={"type": "edit", "wijziging": {"toelichting": "beter"}})).json()
    el1_obj = next(e for e in doc["elementen"] if e["id"] == el1)
    assert el1_obj["beslissingen"][-1]["review_reason"] == "interpretatie"

    # een meegestuurde reden is hooguit een hint: de diff wint, anders staat er een reden in het
    # auditspoor die de server nooit kan toetsen.
    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el1}/beslissing", json={
        "type": "edit", "review_reason": "bron_gemist", "wijziging": {"toelichting": "duidelijker"},
    })).json()
    el1_obj = next(e for e in doc["elementen"] if e["id"] == el1)
    assert el1_obj["beslissingen"][-1]["review_reason"] == "interpretatie"
    # `herkomst` blijft "agent" — dat is WIE HET AANMAAKTE. Een edit door de jurist zet
    # `gewijzigd_door`; anders was na één correctie niet meer te zien dat de agent het voorstelde.
    assert el1_obj["lifecycle"] == "edited"
    assert el1_obj["herkomst"] == "agent" and el1_obj["gewijzigd_door"] == "mens"
    assert el1_obj["diff"]["toelichting"]["na"] == "duidelijker"

    # reject zonder review_reason → 422
    assert (await client.post(f"{BASIS}/{slug}/elementen/{el0}/beslissing",
                              json={"type": "reject"})).status_code == 422

    # audit is append-only en op volgorde. Naast de ronde-samenvatting staat er per element een
    # regel MET id en inhoud — zonder dat is achteraf niet te reconstrueren wat een ronde deed.
    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    acties = [a["actie"] for a in audit]
    assert acties[0] == "document-aangemaakt"
    assert acties[1] == "elementen-voorgesteld"
    assert acties[2:4] == ["element-voorgesteld", "element-voorgesteld"]
    # twee edits: één zonder meegestuurde reden en één met een reden die de diff overruled.
    assert acties[4:] == ["beslissing-approve", "beslissing-edit", "beslissing-edit"]

    samenvatting = audit[1]["detail"]
    assert samenvatting["aangeboden"] == 3 and samenvatting["verworpen"] == 1
    assert samenvatting["nieuw"] == 2 and samenvatting["ronde"] == 0

    per_element = {a["element_id"]: a["detail"] for a in audit if a["actie"] == "element-voorgesteld"}
    assert set(per_element) == {el0, el1}
    assert per_element[el0]["klasse"] and per_element[el0]["tekst"]


async def test_aandacht_persisteert_en_zet_critic_checked(client):
    slug = await _maak_doc(client)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1", "aandacht": "geel",
         "alternatieven": [{"klasse": "Rechtsobject", "motivatie": "twijfel"}]},
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel verlenen", "lid": "1"},  # geen aandacht
    ]})
    assert r.status_code == 200
    elementen = r.json()["elementen"]
    met = next(e for e in elementen if e["klasse"] == "Rechtssubject")
    zonder = next(e for e in elementen if e["klasse"] == "Rechtsbetrekking")
    # aandacht gezet → gepersisteerd + lifecycle critic_checked; alternatieven bewaard.
    assert met["aandacht"] == "geel" and met["lifecycle"] == "critic_checked"
    assert met["alternatieven"][0]["klasse"] == "Rechtsobject"
    # geen aandacht → blijft voorgesteld.
    assert zonder["aandacht"] is None and zonder["lifecycle"] == "voorgesteld"


async def test_client_scoping_404(client):
    # andermans document → 404 op alle sub-resources (lekt niet)
    assert (await client.get(f"{BASIS}/andermans-doc")).status_code == 404
    assert (await client.put(f"{BASIS}/andermans-doc/elementen", json={"elementen": []})).status_code == 404
    assert (await client.get(f"{BASIS}/andermans-doc/audit")).status_code == 404
    # en niet in de eigen lijst
    assert all(d["slug"] != "andermans-doc" for d in (await client.get(BASIS)).json())


async def test_verwijderen(client):
    slug = await _maak_doc(client)
    assert (await client.delete(f"{BASIS}/{slug}")).status_code == 204
    assert (await client.get(f"{BASIS}/{slug}")).status_code == 404


async def test_beslis_op_element_atomair_behoudt_andere_besluiten(client):
    """De atomaire beslis-write (row-lock) verwerkt één element zónder de andere elementen te
    overschrijven — geen lost update bij gelijktijdige besluiten. Plus de 404-sentinels."""
    from app.annotatie_contracts import Lifecycle
    from app.annotatie_store import GEEN_ELEMENT, AnnotatieStore

    slug = await _maak_doc(client)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"},
        {"klasse": "Rechtsbetrekking", "tekst": "kan uitstel verlenen", "lid": "1"},
    ]})
    el0, el1 = r.json()["elementen"][0]["id"], r.json()["elementen"][1]["id"]

    store = AnnotatieStore()

    def keur_goed(doc, el):
        el.lifecycle = Lifecycle.human_approved

    def verwerp(doc, el):
        el.lifecycle = Lifecycle.rejected

    assert await store.beslis_op_element(slug, "gebruiker-a", el0, keur_goed) is not None
    assert await store.beslis_op_element(slug, "gebruiker-a", el1, verwerp) is not None

    doc = (await client.get(f"{BASIS}/{slug}")).json()
    lc = {e["id"]: e["lifecycle"] for e in doc["elementen"]}
    assert lc[el0] == "human_approved"  # niet gewist door de tweede write
    assert lc[el1] == "rejected"

    # 404-sentinels: onbekend document / niet-eigenaar → None; onbekend element → GEEN_ELEMENT.
    assert await store.beslis_op_element("bestaat-niet", "gebruiker-a", el0, keur_goed) is None
    assert await store.beslis_op_element(slug, "gebruiker-b", el0, keur_goed) is None
    assert await store.beslis_op_element(slug, "gebruiker-a", "geen-el", keur_goed) is GEEN_ELEMENT


# --- de merge: een tweede agent-ronde mag nooit werk van de jurist wissen --------------------
#
# Dit was tot voor kort een echte bug: PUT verving de hele elementenlijst met verse uuid's, zodat
# elke volgende ronde alle beslissingen, levenscyclus en diffs weggooide — en het auditlog naar
# id's verwees die niet meer bestonden. Er was geen enkele test die twee keer PUT deed.

async def _put(client, slug, elementen, **extra):
    return await client.put(f"{BASIS}/{slug}/elementen", json={"elementen": elementen, **extra})


async def test_tweede_ronde_behoudt_ids_en_beslissingen(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"},
        {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft", "lid": "1"},
    ])).json()
    ids = {e["tekst"]: e["id"] for e in doc["elementen"]}

    # De jurist keurt er één goed.
    await client.post(f"{BASIS}/{slug}/elementen/{ids['de ontvanger']}/beslissing", json={"type": "approve"})

    # Tweede ronde: de agent stuurt dezelfde elementen opnieuw, nu mét id's en een Critic-oordeel.
    doc = (await _put(client, slug, [
        {"id": ids["de ontvanger"], "klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1",
         "aandacht": "groen", "critic": "helder"},
        {"id": ids["indien betaling uitblijft"], "klasse": "Voorwaarde",
         "tekst": "indien betaling uitblijft", "lid": "1", "aandacht": "geel", "critic": "grens?"},
    ], ronde=1)).json()

    op_id = {e["id"]: e for e in doc["elementen"]}
    assert set(op_id) == set(ids.values()), "id's moeten stabiel blijven"
    goedgekeurd = op_id[ids["de ontvanger"]]
    assert goedgekeurd["lifecycle"] == "human_approved", "de goedkeuring mag niet verdwijnen"
    assert len(goedgekeurd["beslissingen"]) == 1
    # Het Critic-oordeel komt er wél bij: dat raakt het besluit niet en de jurist wil het zien.
    assert goedgekeurd["aandacht"] == "groen"


async def test_beslist_element_is_inhoudelijk_bevroren(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"}])).json()
    el = doc["elementen"][0]["id"]
    await client.post(f"{BASIS}/{slug}/elementen/{el}/beslissing", json={"type": "approve"})

    # De agent probeert klasse én tekst te veranderen op een element waarover al besloten is.
    doc = (await _put(client, slug, [
        {"id": el, "klasse": "Rechtsfeit", "tekst": "iets anders", "aandacht": "rood", "critic": "twijfel"},
    ], ronde=1)).json()

    na = doc["elementen"][0]
    assert na["klasse"] == "Voorwaarde" and na["tekst"] == "indien betaling uitblijft"
    assert na["aandacht"] == "rood", "een nieuw Critic-oordeel mag er wel bij"


async def test_verdwenen_agent_element_wordt_ingetrokken(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Rechtssubject", "tekst": "de ontvanger"},
        {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"},
    ])).json()
    blijft = next(e["id"] for e in doc["elementen"] if e["tekst"] == "de ontvanger")

    doc = (await _put(client, slug, [
        {"id": blijft, "klasse": "Rechtssubject", "tekst": "de ontvanger"},
    ], ronde=1)).json()
    assert [e["id"] for e in doc["elementen"]] == [blijft]

    acties = [a["actie"] for a in (await client.get(f"{BASIS}/{slug}/audit")).json()]
    assert "element-ingetrokken" in acties


async def test_herziening_past_bestaand_element_aan(client):
    """De kern van de Critic-lus: dezelfde id, andere klasse, met een diff in de audit."""
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Rechtsfeit", "tekst": "indien betaling uitblijft"}])).json()
    el = doc["elementen"][0]["id"]

    doc = (await _put(client, slug, [
        {"id": el, "klasse": "Voorwaarde", "tekst": "indien betaling uitblijft",
         "aandacht": "groen", "critic": "na herziening juist"},
    ], ronde=1)).json()

    assert doc["elementen"][0]["id"] == el
    assert doc["elementen"][0]["klasse"] == "Voorwaarde"
    assert doc["elementen"][0]["gewijzigd_door"] == "agent"

    herzien = [a for a in (await client.get(f"{BASIS}/{slug}/audit")).json() if a["actie"] == "element-herzien"]
    assert herzien and herzien[0]["detail"]["diff"]["klasse"] == {"voor": "Rechtsfeit", "na": "Voorwaarde"}


async def test_zelfde_ronde_nogmaals_is_idempotent(client):
    slug = await _maak_doc(client)
    payload = [{"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"}]
    eerst = (await _put(client, slug, payload)).json()
    # Zonder id's: de terugval op tekst+lid moet hetzelfde element vinden, geen duplicaat maken.
    opnieuw = (await _put(client, slug, payload)).json()
    assert len(opnieuw["elementen"]) == 1
    assert opnieuw["elementen"][0]["id"] == eerst["elementen"][0]["id"]


async def test_if_match_beschermt_tegen_een_tussentijdse_wijziging(client):
    slug = await _maak_doc(client)
    r = await _put(client, slug, [{"klasse": "Rechtssubject", "tekst": "de ontvanger"}])
    etag = r.headers["ETag"]
    assert etag

    # Iemand anders wijzigt het document tussendoor.
    el = r.json()["elementen"][0]["id"]
    await client.post(f"{BASIS}/{slug}/elementen/{el}/beslissing", json={"type": "comment", "comment": "hm"})

    verouderd = await client.put(f"{BASIS}/{slug}/elementen",
                                 json={"elementen": [{"klasse": "Voorwaarde", "tekst": "x"}]},
                                 headers={"If-Match": etag})
    assert verouderd.status_code == 412
    # Zonder de header blijft het gewoon werken (terugwaarts compatibel).
    assert (await _put(client, slug, [{"klasse": "Voorwaarde", "tekst": "x"}])).status_code == 200


async def test_legacy_element_met_mens_herkomst_wordt_gerepareerd(client):
    """Rijen van vóór de scheiding: een edit zette destijds `herkomst` op "mens"."""
    from app.annotatie_contracts import AnnotatieElement

    el = AnnotatieElement.model_validate({
        "id": "oud1", "klasse": "Voorwaarde", "tekst": "t", "herkomst": "mens",
        "beslissingen": [{"type": "edit", "actor": "gebruiker-a"}],
    })
    assert el.herkomst == "agent" and el.gewijzigd_door == "mens"

    # Een écht mens-element (geen beslissingen) blijft ongemoeid.
    eigen = AnnotatieElement.model_validate({"id": "e1", "klasse": "Voorwaarde", "tekst": "t", "herkomst": "mens"})
    assert eigen.herkomst == "mens" and eigen.gewijzigd_door == ""


# --- de jurist maakt zelf een markering ---------------------------------------------------------

async def test_eigen_markering_overleeft_een_agentronde(client):
    """De kern van 'één document, twee bijdragers': wat de jurist zelf markeert blijft staan, ook
    als de agent daarna een volledige ronde over hetzelfde artikel doet."""
    slug = await _maak_doc(client)
    r = await client.post(f"{BASIS}/{slug}/elementen", json={
        "klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1",
        "anker": {"lid": "1", "start": 0, "eind": 12, "voor": "", "na": " kan", "bron_hash": "abc123"},
    })
    assert r.status_code == 201
    eigen = next(e for e in r.json()["elementen"] if e["herkomst"] == "mens")
    assert eigen["lifecycle"] == "human_approved", "je eigen markering hoef je niet goed te keuren"
    assert eigen["anker"]["start"] == 0

    # De agent doet een ronde met heel andere elementen en trekt de rest in.
    doc = (await _put(client, slug, [
        {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"},
    ], ronde=1)).json()

    op_herkomst = {e["herkomst"] for e in doc["elementen"]}
    assert op_herkomst == {"mens", "agent"}
    behouden = next(e for e in doc["elementen"] if e["herkomst"] == "mens")
    assert behouden["id"] == eigen["id"] and behouden["anker"]["bron_hash"] == "abc123"


async def test_agentvoorstel_neemt_een_eigen_markering_niet_over(client):
    """Zelfde tekst, maar van de jurist: de terugval op tekst mag die niet stilzwijgend claimen."""
    slug = await _maak_doc(client)
    r = await client.post(f"{BASIS}/{slug}/elementen",
                          json={"klasse": "Rechtssubject", "tekst": "de ontvanger", "lid": "1"})
    eigen_id = next(e["id"] for e in r.json()["elementen"] if e["herkomst"] == "mens")

    doc = (await _put(client, slug, [
        {"klasse": "Rechtsbetrekking", "tekst": "de ontvanger", "lid": "1"},
    ], ronde=1)).json()

    assert len(doc["elementen"]) == 2, "de agent krijgt een eigen element, niet dat van de jurist"
    van_mens = next(e for e in doc["elementen"] if e["id"] == eigen_id)
    assert van_mens["klasse"] == "Rechtssubject", "onaangeroerd"


async def test_eigen_markering_verwijderen_kan_agentvoorstel_niet(client):
    slug = await _maak_doc(client)
    r = await client.post(f"{BASIS}/{slug}/elementen",
                          json={"klasse": "Rechtssubject", "tekst": "de ontvanger"})
    eigen_id = next(e["id"] for e in r.json()["elementen"] if e["herkomst"] == "mens")

    doc = (await _put(client, slug, [{"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"}],
                      ronde=1)).json()
    agent_id = next(e["id"] for e in doc["elementen"] if e["herkomst"] == "agent")

    # Een agent-voorstel verwerp je (met reden), je verwijdert het niet — anders verdwijnt het
    # spoor dat er een voorstel wás.
    assert (await client.delete(f"{BASIS}/{slug}/elementen/{agent_id}")).status_code == 409
    assert (await client.delete(f"{BASIS}/{slug}/elementen/{eigen_id}")).status_code == 204
    assert (await client.delete(f"{BASIS}/{slug}/elementen/bestaat-niet")).status_code == 404

    over = (await client.get(f"{BASIS}/{slug}")).json()["elementen"]
    assert [e["id"] for e in over] == [agent_id]

    acties = [a["actie"] for a in (await client.get(f"{BASIS}/{slug}/audit")).json()]
    assert "element-toegevoegd" in acties and "element-verwijderd" in acties


async def test_eigen_markering_valideert_de_klasse(client):
    slug = await _maak_doc(client)
    assert (await client.post(f"{BASIS}/{slug}/elementen",
                              json={"klasse": "Onzin", "tekst": "de ontvanger"})).status_code == 422
    assert (await client.post(f"{BASIS}/{slug}/elementen",
                              json={"klasse": "Rechtssubject", "tekst": "   "})).status_code == 422
    # en andermans document lekt niet
    assert (await client.post(f"{BASIS}/andermans-doc/elementen",
                              json={"klasse": "Rechtssubject", "tekst": "x"})).status_code == 404


# --- één kapot element sleept de rest niet mee ---------------------------------------------------

async def test_een_element_dat_het_schema_niet_haalt_sleept_de_rest_niet_mee(client):
    """Twee poorten hadden tegengesteld beleid; dat verschil was de fout, niet de strengheid.

    De merge verwerpt een ongeldige klasse al per element, met een teller. De request-validatie
    ervóór was alles-of-niets: één schemafout gaf 422 en dan landde er níéts. Op dev kostte dat een
    complete annotatie van vijftien markeringen — de agent was klaar en gegrond.
    """
    slug = await _maak_doc(client)
    r = await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [
            {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"},
            {"klasse": "Rechtssubject", "aandacht": "paars", "tekst": "de ontvanger"},  # geen niveau
            {"klasse": "Rechtsfeit", "tekst": "de melding"},
        ],
        "ronde": 1,
    })

    assert r.status_code == 200, "de goede elementen horen gewoon te landen"
    teksten = {e["tekst"] for e in r.json()["elementen"]}
    assert teksten == {"indien betaling uitblijft", "de melding"}
    assert r.headers.get("X-Verworpen") == "1", "en de aanroeper hoort te wéten dat er iets weg is"


async def test_het_auditspoor_zegt_wat_er_sneuvelde(client):
    """Een teller vertelt dát er iets weg is; dit vertelt wát, zodat de jurist het zelf kan zetten."""
    slug = await _maak_doc(client)
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [
            {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"},
            {"klasse": "Rechtssubject", "aandacht": "paars", "tekst": "de ontvanger"},
        ],
        "ronde": 1,
    })

    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    ronde = next(a for a in audit if a["actie"] == "elementen-voorgesteld")
    assert ronde["detail"]["aangeboden"] == 2, "aangeboden telt ook wat er sneuvelde"
    assert ronde["detail"]["verworpen"] == 1
    geweigerd = ronde["detail"]["geweigerd"][0]
    assert geweigerd["tekst"] == "de ontvanger"
    assert "aandacht" in geweigerd["reden"]


async def test_zonder_verworpen_geen_header(client):
    """Een header die er altijd staat, valt niemand meer op."""
    slug = await _maak_doc(client)
    r = await _put(client, slug, [{"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft"}])
    assert "X-Verworpen" not in r.headers


async def test_een_kapot_veld_buiten_de_elementen_blijft_een_422(client):
    """Gedeeltelijk slagen is een uitzondering voor de elementenlijst, geen algemene versoepeling."""
    slug = await _maak_doc(client)
    r = await client.put(f"{BASIS}/{slug}/elementen",
                         json={"elementen": [], "ronde": "geen getal"})
    assert r.status_code == 422


# --- de Critic kijkt mee op eigen markeringen: advies, nooit een wijziging ----------------------

async def test_suggestie_landt_op_eigen_markering_zonder_die_te_wijzigen(client):
    slug = await _maak_doc(client)
    r = await client.post(f"{BASIS}/{slug}/elementen",
                          json={"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft", "lid": "1"})
    eigen_id = next(e["id"] for e in r.json()["elementen"] if e["herkomst"] == "mens")

    doc = (await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"klasse": "Rechtssubject", "tekst": "de ontvanger"}],
        "suggesties": [{"element_id": eigen_id, "aandacht": "geel",
                        "motivatie": "zou dit niet een Rechtsfeit zijn?",
                        "voorstel_klasse": "Rechtsfeit"}],
        "ronde": 1,
    })).json()

    van_mens = next(e for e in doc["elementen"] if e["id"] == eigen_id)
    assert van_mens["klasse"] == "Voorwaarde", "de markering zelf blijft ongemoeid"
    assert van_mens["aandacht"] is None, "een suggestie is geen aandacht-oordeel"
    assert van_mens["critic_suggestie"]["motivatie"].startswith("zou dit")
    assert van_mens["critic_suggestie"]["voorstel_klasse"] == "Rechtsfeit"
    assert van_mens["critic_suggestie"]["status"] == "open"

    acties = [a["actie"] for a in (await client.get(f"{BASIS}/{slug}/audit")).json()]
    assert "critic-suggestie" in acties


async def test_kaal_oordeel_op_een_agentelement_wordt_genegeerd(client):
    """Een oordeel zónder voorstel hoort op een agent-element gewoon in `aandacht` thuis."""
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Rechtssubject", "tekst": "de ontvanger"}])).json()
    agent_id = doc["elementen"][0]["id"]

    doc = (await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"id": agent_id, "klasse": "Rechtssubject", "tekst": "de ontvanger"}],
        "suggesties": [{"element_id": agent_id, "aandacht": "rood", "motivatie": "nee"}],
        "ronde": 1,
    })).json()
    assert doc["elementen"][0]["critic_suggestie"] is None


async def test_fragmentvoorstel_op_een_agentelement_landt_wel(client):
    """De eindbeoordeling komt te laat voor de patcher; anders bleef het voorstel in de tekst hangen.

    Op dev stond er twee keer "overweeg het fragment te beperken tot 'is aansprakelijk'" met het
    exacte fragment in de data, terwijl de jurist het met de hand moest naselecteren.
    """
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Rechtsbetrekking",
                                      "tekst": "de ontvanger verleent uitstel"}])).json()
    agent_id = doc["elementen"][0]["id"]

    doc = (await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"id": agent_id, "klasse": "Rechtsbetrekking",
                       "tekst": "de ontvanger verleent uitstel"}],
        "suggesties": [{"element_id": agent_id, "aandacht": "geel", "motivatie": "korter is scherper",
                        "voorstel_tekst": "verleent uitstel"}],
        "ronde": 1,
    })).json()

    el = doc["elementen"][0]
    assert el["tekst"] == "de ontvanger verleent uitstel", "een suggestie wijzigt nooit iets"
    assert el["critic_suggestie"]["voorstel_tekst"] == "verleent uitstel"
    assert el["critic_suggestie"]["status"] == "open"


async def test_klassevoorstel_op_een_agentelement_landt_ook(client):
    """In een eerdere ronde maakt de patcher er een alternatief van; in de eindronde draait die niet."""
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Rechtsobject", "tekst": "de ontvanger"}])).json()
    agent_id = doc["elementen"][0]["id"]

    doc = (await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"id": agent_id, "klasse": "Rechtsobject", "tekst": "de ontvanger"}],
        "suggesties": [{"element_id": agent_id, "aandacht": "geel", "motivatie": "eerder een subject",
                        "voorstel_klasse": "Rechtssubject"}],
        "ronde": 1,
    })).json()

    el = doc["elementen"][0]
    assert el["klasse"] == "Rechtsobject", "een suggestie wijzigt nooit iets"
    assert el["critic_suggestie"]["voorstel_klasse"] == "Rechtssubject"


async def test_een_overgenomen_suggestie_gaat_dicht(client):
    """Anders blijft de kaart om een keuze vragen die al gemaakt is.

    Op dev las dat als "er gebeurt niets": de jurist nam het voorgestelde fragment over, de
    kanttekening bleef staan met dezelfde knop, en hij bleef klikken.
    """
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Voorwaarde",
                                      "tekst": "de ontvanger verleent uitstel"}])).json()
    agent_id = doc["elementen"][0]["id"]
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"id": agent_id, "klasse": "Voorwaarde", "tekst": "de ontvanger verleent uitstel"}],
        "suggesties": [{"element_id": agent_id, "aandacht": "geel", "motivatie": "korter kan",
                        "voorstel_tekst": "verleent uitstel"}],
        "ronde": 1,
    })

    doc = (await _beslis(client, slug, agent_id, type="edit",
                         wijziging={"tekst": "verleent uitstel"})).json()
    el = next(e for e in doc["elementen"] if e["id"] == agent_id)
    assert el["tekst"] == "verleent uitstel"
    assert el["critic_suggestie"]["status"] == "geaccepteerd"


async def test_een_eigen_wijziging_laat_de_suggestie_openstaan(client):
    """Alleen overnemen sluit hem; iets anders doen is geen antwoord op het voorstel."""
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Voorwaarde",
                                      "tekst": "de ontvanger verleent uitstel"}])).json()
    agent_id = doc["elementen"][0]["id"]
    await client.put(f"{BASIS}/{slug}/elementen", json={
        "elementen": [{"id": agent_id, "klasse": "Voorwaarde", "tekst": "de ontvanger verleent uitstel"}],
        "suggesties": [{"element_id": agent_id, "aandacht": "geel", "motivatie": "korter kan",
                        "voorstel_tekst": "verleent uitstel"}],
        "ronde": 1,
    })

    doc = (await _beslis(client, slug, agent_id, type="edit",
                         wijziging={"tekst": "de ontvanger"})).json()
    el = next(e for e in doc["elementen"] if e["id"] == agent_id)
    assert el["critic_suggestie"]["status"] == "open"


# --- het fragment inkorten/uitbreiden: het anker moet meeschuiven -------------------------------
#
# Zonder dat wijzen de offsets naar het oude fragment en springt de markering na herladen naar een
# ander voorkomen — precies wat het anker moest voorkomen.

def _anker(start, eind, hash_="v1"):
    return {"lid": "1", "start": start, "eind": eind, "voor": "", "na": "", "bron_hash": hash_}


async def test_edit_van_de_tekst_verplaatst_het_anker(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Rechtsobject", "tekst": "belastingaanslag", "anker": _anker(10, 26)},
    ])).json()
    el_id = doc["elementen"][0]["id"]

    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el_id}/beslissing", json={
        "type": "edit", "review_reason": "tekst",
        "wijziging": {"tekst": "een belastingaanslag", "anker": _anker(6, 26)},
    })).json()

    el = doc["elementen"][0]
    assert el["tekst"] == "een belastingaanslag"
    assert (el["anker"]["start"], el["anker"]["eind"]) == (6, 26)
    assert "anker" not in el["diff"], "het anker is machinerie, geen inhoudelijke wijziging"
    assert el["diff"]["tekst"] == {"voor": "belastingaanslag", "na": "een belastingaanslag"}


async def test_edit_zonder_anker_wist_een_verouderd_anker(client):
    """Geen anker is eerlijker dan een anker dat over de oude tekst gaat: dan valt de weergave terug
    op de context/het eerste voorkomen in plaats van naar een verkeerde plek te wijzen."""
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Rechtsobject", "tekst": "belastingaanslag", "anker": _anker(10, 26)},
    ])).json()
    el_id = doc["elementen"][0]["id"]

    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el_id}/beslissing", json={
        "type": "edit", "review_reason": "tekst", "wijziging": {"tekst": "aanslag"},
    })).json()
    assert doc["elementen"][0]["anker"] is None


async def test_edit_die_de_tekst_niet_raakt_laat_het_anker_staan(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Rechtsobject", "tekst": "belastingaanslag", "anker": _anker(10, 26)},
    ])).json()
    el_id = doc["elementen"][0]["id"]

    doc = (await client.post(f"{BASIS}/{slug}/elementen/{el_id}/beslissing", json={
        "type": "edit", "review_reason": "verkeerde_klasse", "wijziging": {"klasse": "Rechtssubject"},
    })).json()
    el = doc["elementen"][0]
    assert el["klasse"] == "Rechtssubject"
    assert (el["anker"]["start"], el["anker"]["eind"]) == (10, 26)


async def test_de_audit_meldt_dat_het_anker_verplaatste(client):
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [{"klasse": "Rechtsobject", "tekst": "belastingaanslag"}])).json()
    el_id = doc["elementen"][0]["id"]
    await client.post(f"{BASIS}/{slug}/elementen/{el_id}/beslissing", json={
        "type": "edit", "review_reason": "tekst",
        "wijziging": {"tekst": "een belastingaanslag", "anker": _anker(6, 26)},
    })

    regels = (await client.get(f"{BASIS}/{slug}/audit")).json()
    laatste = next(r for r in reversed(regels) if r["actie"] == "beslissing-edit")
    assert laatste["detail"]["anker_verplaatst"] is True


# --- een oordeel vergrendelt: wijzigen kan pas na een expliciete heropening -------------------
#
# Hiervóór kon een geaccordeerd element onbeperkt opnieuw beslist worden (approve → edit → reject →
# approve → …). De frontend verborg alleen de knoppen, maar de klasse-badge en de toelichting
# schreven stilzwijgend een edit weg — een akkoord betekende dus niets.

async def _beslis(client, slug, el_id, **body):
    return await client.post(f"{BASIS}/{slug}/elementen/{el_id}/beslissing", json=body)


async def _een_element(client, **extra) -> tuple[str, str]:
    slug = await _maak_doc(client)
    doc = (await _put(client, slug, [
        {"klasse": "Voorwaarde", "tekst": "indien betaling uitblijft", **extra},
    ])).json()
    return slug, doc["elementen"][0]["id"]


@pytest.mark.parametrize("oordeel", ["approve", "reject"])
async def test_een_beoordeeld_element_is_op_slot(client, oordeel):
    slug, el = await _een_element(client)
    assert (await _beslis(client, slug, el, type=oordeel, review_reason="anders")).status_code == 200

    r = await _beslis(client, slug, el, type="edit", review_reason="verkeerde_klasse",
                      wijziging={"klasse": "Rechtsfeit"})
    assert r.status_code == 409 and "Heropen" in r.json()["detail"]
    assert (await _beslis(client, slug, el, type="reject", review_reason="anders")).status_code == 409

    # …en de wijziging landde ook echt niet.
    doc = (await client.get(f"{BASIS}/{slug}")).json()
    assert doc["elementen"][0]["klasse"] == "Voorwaarde"


async def test_een_opmerking_mag_wel_op_een_vergrendeld_element(client):
    """Een kanttekening wijzigt de annotatie niet — juist bij iets dat vaststaat wil je die kwijt."""
    slug, el = await _een_element(client)
    await _beslis(client, slug, el, type="approve")

    assert (await _beslis(client, slug, el, type="comment", comment="navragen bij de vaktechniek")
            ).status_code == 200
    doc = (await client.get(f"{BASIS}/{slug}")).json()
    assert doc["elementen"][0]["lifecycle"] == "human_approved"
    assert [b["type"] for b in doc["elementen"][0]["beslissingen"]] == ["approve", "comment"]


async def test_heropenen_geeft_het_element_terug_aan_de_review(client):
    slug, el = await _een_element(client)
    await _beslis(client, slug, el, type="approve")

    doc = (await _beslis(client, slug, el, type="heropen")).json()
    assert doc["elementen"][0]["lifecycle"] == "voorgesteld"
    assert doc["elementen"][0]["gewijzigd_door"] == "mens"

    # Daarna mag er weer gewerkt worden.
    doc = (await _beslis(client, slug, el, type="edit", review_reason="verkeerde_klasse",
                         wijziging={"klasse": "Rechtsfeit"})).json()
    assert doc["elementen"][0]["klasse"] == "Rechtsfeit"

    # En de heropening staat in het spoor — anders is een teruggedraaid akkoord onzichtbaar.
    assert [b["type"] for b in doc["elementen"][0]["beslissingen"]] == ["approve", "heropen", "edit"]
    acties = [r["actie"] for r in (await client.get(f"{BASIS}/{slug}/audit")).json()]
    assert "beslissing-heropen" in acties


async def test_heropenen_bewaart_het_critic_oordeel(client):
    """Terug naar `critic_checked`, niet naar `voorgesteld`: anders poetst heropenen het oordeel van
    de Critic uit beeld en lijkt het element ongezien."""
    slug, el = await _een_element(client, critic="twijfel tussen twee klassen", aandacht="geel")
    await _beslis(client, slug, el, type="approve")

    doc = (await _beslis(client, slug, el, type="heropen")).json()
    assert doc["elementen"][0]["lifecycle"] == "critic_checked"
    assert doc["elementen"][0]["critic"] == "twijfel tussen twee klassen"


async def test_heropenen_van_iets_dat_niet_op_slot_staat(client):
    slug, el = await _een_element(client)
    r = await _beslis(client, slug, el, type="heropen")
    assert r.status_code == 409 and "niet op slot" in r.json()["detail"]


async def test_een_eigen_markering_gaat_niet_op_slot(client):
    """Je eigen markering is `human_approved` bij het aanmaken — dat is gemaakt, niet beoordeeld.
    Vergrendelen zou hem meteen op slot zetten, inclusief de wisknop."""
    slug = await _maak_doc(client)
    doc = (await client.post(f"{BASIS}/{slug}/elementen", json={
        "klasse": "Rechtsfeit", "tekst": "zes weken na de dagtekening", "lid": "1",
    })).json()
    el = doc["elementen"][0]["id"]
    assert doc["elementen"][0]["lifecycle"] == "human_approved"

    r = await _beslis(client, slug, el, type="edit", review_reason="verkeerde_klasse",
                      wijziging={"klasse": "Rechtsbetrekking"})
    assert r.status_code == 200
    assert (await client.delete(f"{BASIS}/{slug}/elementen/{el}")).status_code == 204


# --- de reviewreden komt van de server ------------------------------------------------------------

@pytest.mark.parametrize("wijziging, verwacht", [
    ({"tekst": "indien betaling uitblijft na aanmaning"}, "tekst"),
    ({"klasse": "Rechtsfeit"}, "verkeerde_klasse"),
    ({"toelichting": "scherper"}, "interpretatie"),
    ({"lid": "2"}, "anders"),                                    # geen vaste reden dekt dit
    ({"klasse": "Rechtsfeit", "toelichting": "scherper"}, "anders"),  # meer dan één veld
])
async def test_reviewreden_volgt_uit_de_diff(client, wijziging, verwacht):
    """De reden hoort te worden vastgesteld waar het bewijs ligt: bij de diff die de server maakt.

    Stond die afleiding in de browser, dan was de reden in het auditspoor een waarde die de server
    aannam maar nooit kon toetsen — in een systeem dat om herleidbaarheid draait is dat te zwak.
    """
    slug, el = await _een_element(client, lid="1", toelichting="eerste")
    doc = (await _beslis(client, slug, el, type="edit", wijziging=wijziging)).json()
    assert doc["elementen"][0]["beslissingen"][-1]["review_reason"] == verwacht

    audit = (await client.get(f"{BASIS}/{slug}/audit")).json()
    assert audit[-1]["detail"]["review_reason"] == verwacht


async def test_een_edit_zonder_echte_wijziging_schrijft_geen_beslissing(client):
    """Niets veranderd is geen beslissing — ook al antwoordt de server netjes met 200.

    Op dev leverde één suggestie die niet zichtbaar werd overgenomen zestien beslissingen op
    hetzelfde element op, waarvan vijftien leeg: de jurist bleef klikken omdat hij niets zag
    gebeuren. Een auditspoor vol niet-gebeurtenissen is moeilijker te lezen dan een kort spoor, en
    dat spoor is hier het product.
    """
    slug, el = await _een_element(client, lid="1")
    voor = len((await _beslis(client, slug, el, type="comment",
                              comment="x")).json()["elementen"][0]["beslissingen"])

    r = await _beslis(client, slug, el, type="edit", wijziging={"klasse": "Voorwaarde"})
    assert r.status_code == 200, "geen fout: er valt niets te melden, niet iets dat misging"
    element = r.json()["elementen"][0]
    assert len(element["beslissingen"]) == voor
    assert element["lifecycle"] != "edited", "onaangeroerd blijft onaangeroerd"

    acties = [a["actie"] for a in (await client.get(f"{BASIS}/{slug}/audit")).json()]
    assert "beslissing-edit" not in acties


async def test_reject_vraagt_de_reden_nog_steeds_aan_de_mens(client):
    """Waaróm iets verworpen wordt staat in geen enkele diff — dat weet alleen de jurist."""
    slug, el = await _een_element(client, lid="1")
    assert (await _beslis(client, slug, el, type="reject")).status_code == 422
    assert (await _beslis(client, slug, el, type="reject",
                          review_reason="bron_gemist")).status_code == 200


async def test_een_meegestuurd_veld_dat_gelijk_blijft_telt_niet_mee(client):
    """Klasse wijzigen terwijl de tekst ongewijzigd meekomt → `verkeerde_klasse`, niet `anders`.

    De UI stuurt bij een klasse-wijziging soms het hele element mee. Woog dat mee, dan werd elke
    klasse-correctie in het auditspoor een vage `anders`. De diff bevat alleen wat écht veranderde,
    dus dit volgt vanzelf — maar het is de regressie waar de browserversie een eigen test voor had.
    """
    slug, el = await _een_element(client, lid="1", toelichting="eerste")
    doc = (await _beslis(client, slug, el, type="edit", wijziging={
        "klasse": "Rechtsfeit", "tekst": "indien betaling uitblijft", "lid": "1",
    })).json()
    assert doc["elementen"][0]["beslissingen"][-1]["review_reason"] == "verkeerde_klasse"
    assert set(doc["elementen"][0]["diff"]) == {"klasse"}
