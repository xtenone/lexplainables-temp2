"""Het /v1/artikel-endpoint (workbench-documentpaneel-tekst) met gepatchte graaf.

Bare TestClient (geen lifespan → geen startup-tokencheck); de graaf wordt gemonkeypatcht zodat er
geen netwerk aan te pas komt. De inhoudelijke logica zit in test_artikel.
"""
from __future__ import annotations

import api.main as main
from fastapi.testclient import TestClient


def test_artikel_endpoint(monkeypatch):
    class _Graph:
        def initialize(self):
            return {}

        def close(self):
            pass

    monkeypatch.setattr("agent.adapters.graphdb_graph.make_graph", lambda _s: _Graph())
    monkeypatch.setattr(
        "agent.artikel.haal_artikel_sync",
        lambda bwb, art, graph, lid=None: {
            "bwbId": bwb, "artikel": art, "citeertitel": "Invorderingswet 1990",
            "opschrift": "", "leden_teksten": [{"lid": "1", "tekst": "Eerste lid."}],
        },
    )
    client = TestClient(main.app)
    r = client.get("/v1/artikel", params={"bwb_id": "BWBR0004770", "artikel": "9"})
    assert r.status_code == 200
    body = r.json()
    assert body["citeertitel"] == "Invorderingswet 1990"
    assert body["leden_teksten"][0]["tekst"] == "Eerste lid."
