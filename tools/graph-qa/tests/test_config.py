"""Secrets via `*_FILE` (Docker host-bestand-conventie)."""
from __future__ import annotations

from agent.config import Settings


def test_secret_uit_file(tmp_path):
    f = tmp_path / "graphdb_token"
    f.write_text("  tok-uit-bestand\n", encoding="utf-8")
    s = Settings.from_env({"GRAPHDB_TOKEN_FILE": str(f)})
    assert s.graphdb_token == "tok-uit-bestand"  # gestript


def test_file_wint_van_env_var(tmp_path):
    f = tmp_path / "qa_api_token"
    f.write_text("uit-bestand", encoding="utf-8")
    s = Settings.from_env({"QA_API_TOKEN_FILE": str(f), "QA_API_TOKEN": "uit-env"})
    assert s.qa_api_token == "uit-bestand"


def test_env_var_zonder_file(tmp_path):
    s = Settings.from_env({"AZURE_FOUNDRY_API_KEY": "plain"})
    assert s.azure_foundry_api_key == "plain"


def test_ontbrekend_bestand_geeft_none(tmp_path):
    s = Settings.from_env({"GRAPHDB_TOKEN_FILE": str(tmp_path / "bestaat-niet")})
    assert s.graphdb_token is None


def test_decompositie_defaults_uit():
    s = Settings.from_env({})
    assert s.enable_decomposition is False
    assert s.max_subquestions == 5


def test_decompositie_via_env():
    s = Settings.from_env({"ENABLE_DECOMPOSITION": "1", "MAX_SUBQUESTIONS": "3", "SUB_MAX_TURNS": "4"})
    assert s.enable_decomposition is True
    assert s.max_subquestions == 3
    assert s.sub_max_turns == 4


def test_lege_env_string_valt_terug_op_default():
    # L3: een gezet-maar-leeg env-var mag niet op int("")-coercie crashen maar de default nemen.
    s = Settings.from_env({"MAX_TURNS": "", "MAX_HISTORY_CHARS": "", "MAX_SUBQUESTIONS": ""})
    assert s.max_turns == 20
    assert s.max_history_chars == 40000
    assert s.max_subquestions == 5


def test_schrijfrecht_zonder_eigen_slot_weigert_te_starten():
    """Mag graph-qa naar de api schrijven, dan MOET zijn eigen endpoint een token hebben.

    Zonder `QA_API_TOKEN` is `/v1/runs` open (zie `_check_auth`), en het verzoek draagt zelf de
    `user_id` waarnamens er geschreven wordt — dan is een open endpoint een schrijfprimitief op
    elk gebruikersgesprek. Fail-fast bij boot in plaats van dat stil laten bestaan.
    """
    import pytest

    from agent.config import Settings

    onveilig = Settings(wetsanalyse_api_url="http://api:3000", wetsanalyse_api_token="t")
    assert onveilig.legt_zelf_vast
    with pytest.raises(ValueError, match="QA_API_TOKEN"):
        onveilig.require_api()

    veilig = Settings(wetsanalyse_api_url="http://api:3000", wetsanalyse_api_token="t", qa_api_token="q")
    veilig.require_api()  # geen exception


def test_zonder_api_config_legt_graph_qa_niets_vast():
    """Lokaal draaien zonder api moet mogelijk blijven; dan schrijft de werkplek weg, zoals vroeger."""
    from agent.config import Settings

    assert not Settings().legt_zelf_vast
    assert not Settings(wetsanalyse_api_url="http://api:3000").legt_zelf_vast  # token ontbreekt
    Settings().require_api()  # geen eis zonder schrijfrecht
