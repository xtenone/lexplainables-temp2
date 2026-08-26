"""
Eval-harnas voor graph-qa.

Draait een gouden Q&A-set door de agent en scoort citaat-faithfulness, bron-recall,
contains- en refusal-checks. Twee modi:

  live (default) : echte providers (vereist een gevulde .env + bereikbare graaf).
      .venv/bin/python eval/run_eval.py

  offline        : gescripte fakes, geen netwerk/kosten — bewijst de harnas + scorers.
      .venv/bin/python eval/run_eval.py --offline

Exit-code ≠ 0 als niet alle cases slagen (CI-klaar).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.agent import answer_stream  # noqa: E402
from agent.config import Settings  # noqa: E402
from eval.scoring import AnnotatieResult, CaseResult, score_annotatie, score_case  # noqa: E402

GOLDEN = Path(__file__).parent / "golden.jsonl"
GOLDEN_ANNOTATIE = Path(__file__).parent / "golden_annotatie.jsonl"


def load_golden(path: Path = GOLDEN) -> list[dict[str, Any]]:
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cases.append(json.loads(line))
    return cases


async def run_case(case: dict[str, Any], *, settings: Settings, llm=None, graph=None) -> CaseResult:
    parts: list[str] = []
    sources: list[dict[str, Any]] = []
    grounding: dict[str, Any] = {"grounded": True, "cited": 0, "unsupported": []}
    error: str | None = None

    async for ev in answer_stream(case["question"], settings=settings, llm=llm, graph=graph):
        t = ev.get("type")
        if t == "token":
            parts.append(ev["content"])
        elif t == "sources":
            sources = ev["sources"]
        elif t == "grounding":
            grounding = ev
        elif t == "error":
            error = ev["message"]

    return score_case(case, "".join(parts), sources, grounding, error)


async def run_suite(cases: list[dict[str, Any]], *, settings: Settings, llm=None, graph=None) -> list[CaseResult]:
    return [await run_case(c, settings=settings, llm=llm, graph=graph) for c in cases]


async def run_annotatie_case(
    case: dict[str, Any], *, settings: Settings, llm=None, graph=None
) -> AnnotatieResult:
    """Draai één annotatie-opdracht en scoor de markeringen die eruit komen.

    Meet de hele keten (ophaal → annoteer → Critic → herziening), niet één node: dat is wat de jurist
    ook krijgt. Het corpus komt uit het `doel`-event — dezelfde tekst waartegen de agent zelf grondde,
    zodat "staat dit letterlijk in de bron" hier hetzelfde betekent als daar.
    """
    elementen: list[dict[str, Any]] = []
    corpus = ""
    antwoord: list[str] = []
    error: str | None = None

    async for ev in answer_stream(case["prompt"], settings=settings, llm=llm, graph=graph):
        soort = ev.get("type")
        if soort == "element":
            elementen.append(ev["element"])
        elif soort == "doel":
            leden = (ev.get("doel") or {}).get("leden_teksten") or []
            corpus = "\n\n".join(ld.get("tekst", "") for ld in leden)
        elif soort == "token":
            antwoord.append(ev.get("content", ""))
        elif soort == "error":
            error = ev["message"]

    return score_annotatie(case, elementen, corpus, "".join(antwoord), error)


async def run_annotatie_suite(
    cases: list[dict[str, Any]], *, settings: Settings, llm=None, graph=None
) -> list[AnnotatieResult]:
    return [await run_annotatie_case(c, settings=settings, llm=llm, graph=graph) for c in cases]


def print_report(results: list[CaseResult]) -> bool:
    print(f"\n{'faith':>6} {'recall':>6} {'cont':>4} {'refu':>4} {'schoon':>6}  vraag")
    print("-" * 80)
    for r in results:
        flag = "OK " if r.passed else "XX "
        extra = f"  ! {r.error}" if r.error else ""
        print(
            f"{r.faithfulness:6.2f} {r.source_recall:6.2f} "
            f"{'ja' if r.contains_ok else 'nee':>4} {'ja' if r.refusal_ok else 'nee':>4} "
            f"{'ja' if r.zonder_verboden_ok else 'NEE':>6}  "
            f"{flag}{r.question[:44]}{extra}"
        )
    passed = sum(r.passed for r in results)
    print("-" * 80)
    print(f"{passed}/{len(results)} geslaagd")
    return passed == len(results)


def print_annotatie_report(results: list[AnnotatieResult]) -> bool:
    print(f"\n{'lett':>5} {'klas':>5} {'prec':>5} {'rec':>5} {'n':>3} {'scope':>5} {'inj':>4}  opdracht")
    print("-" * 78)
    for r in results:
        vlag = "OK " if r.passed else "XX "
        extra = f"  ! {r.error}" if r.error else ""
        print(
            f"{r.letterlijk:5.2f} {r.klassen:5.2f} {r.precisie:5.2f} {r.recall:5.2f} {r.aantal:3d} "
            f"{'ja' if r.binnen_bereik else 'NEE':>5} {'ja' if r.injectie_ok else 'NEE':>4}  "
            f"{vlag}{r.prompt[:38]}{extra}"
        )
    ok = sum(r.passed for r in results)
    print("-" * 78)
    print(f"{ok}/{len(results)} geslaagd (precisie/recall zijn een trendmeting, geen slaagcriterium)")
    return ok == len(results)


def _offline_annotatie_scenario():
    """Eén gescripte annotatie + fakes: bewijst de harnas, niet het model.

    Wat hier wél getest wordt is de meting zelf — dat een fragment uit een ander lid als
    buiten-bereik telt en dat een injectie in de wettekst wordt opgemerkt. Of het écht model daar
    intrapt, meet alleen de live-run.
    """
    import json as _json

    from tests.fakes import FakeGraph, FakeLLM, response, text_block, tool_block

    lid_tsv = _json.dumps(
        '?nummer\t?tekst\n"1"\t"Een belastingaanslag is invorderbaar zes weken na de dagtekening."'
    )
    elementen = _json.dumps({"elementen": [
        {"klasse": "Rechtsobject", "tekst": "Een belastingaanslag", "lid": "1",
         "toelichting": "waarover het gaat", "alternatieven": []},
        {"klasse": "Tijdsaanduiding", "tekst": "zes weken na de dagtekening", "lid": "1",
         "toelichting": "wanneer", "alternatieven": []},
    ]})
    llm = FakeLLM([
        response([text_block("WORKERS: annotatie\nPLAN: annoteer art 9 lid 1")], "end_turn"),
        response([tool_block("t1", "get_lid", {"bwb_id": "BWBR0004770", "artikel": "9", "lid": "1"})], "tool_use"),
        response([text_block('{"bwbId":"BWBR0004770","artikel":"9","lid":"1","citeertitel":"IW 1990"}')], "end_turn"),
        response([text_block(elementen)], "end_turn"),
        response([text_block(_json.dumps({"oordelen": [], "ontbrekend": []}))], "end_turn"),
    ])
    case = {
        "prompt": "annoteer artikel 9 lid 1 van de Invorderingswet 1990",
        "verwacht": [
            {"klasse": "Rechtsobject", "tekst": "Een belastingaanslag"},
            {"klasse": "Tijdsaanduiding", "tekst": "zes weken na de dagtekening"},
        ],
        "verboden": ["uitstel van betaling"],
        "kanaries": ["GEHACKT"],
    }
    return [case], llm, FakeGraph(result=lid_tsv)


def _offline_scenario():
    """Eén gescripte case + fakes die de harnas end-to-end aantonen (geen netwerk)."""
    from tests.fakes import FakeGraph, FakeLLM, response, text_block, tool_block

    graph = FakeGraph(result='<urn:bwb:BWBR0004770> bwb:citeertitel "Invorderingswet 1990" .')
    llm = FakeLLM([
        response([text_block("Ik raadpleeg list_regelingen.")], "end_turn"),          # plan-node (create)
        response([tool_block("t1", "list_regelingen", {})], "tool_use"),              # agent-turn 1 (stream)
        response([text_block("De Invorderingswet 1990 (BWBR0004770) staat in de graaf.")], "end_turn"),  # agent-turn 2
    ])
    case = {
        "question": "Welke regelingen zitten er in de kennisgraaf?",
        "expected_sources": ["BWBR0004770"],
        "expected_contains": ["Invorderingswet 1990"],
        "should_refuse": False,
    }
    return [case], llm, graph


def _laad_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).parent.parent / ".env")
    except ImportError:
        pass


def main() -> None:
    ap = argparse.ArgumentParser(description="graph-qa eval-harnas")
    ap.add_argument("--offline", action="store_true", help="draai met fakes (geen netwerk/kosten)")
    ap.add_argument("--golden", type=Path, default=GOLDEN, help="pad naar de golden set (jsonl)")
    ap.add_argument("--annotatie", action="store_true",
                    help="draai de annotatie-set (JAS-markeringen) in plaats van de QA-set")
    args = ap.parse_args()

    if args.annotatie:
        if args.offline:
            cases, llm, graph = _offline_annotatie_scenario()
            resultaten = asyncio.run(run_annotatie_suite(
                cases, settings=Settings(checkpoint_db_path=None), llm=llm, graph=graph,
            ))
        else:
            _laad_env()
            resultaten = asyncio.run(run_annotatie_suite(
                load_golden(GOLDEN_ANNOTATIE), settings=Settings.from_env(),
            ))
        sys.exit(0 if print_annotatie_report(resultaten) else 1)

    if args.offline:
        cases, llm, graph = _offline_scenario()
        results = asyncio.run(run_suite(cases, settings=Settings(checkpoint_db_path=None), llm=llm, graph=graph))
    else:
        _laad_env()
        settings = Settings.from_env()
        cases = load_golden(args.golden)
        if not settings.similarity_index:
            # semantic_search-cases overslaan tot de similarity-index bestaat.
            cases = [c for c in cases if c.get("requires") != "semantic"]
        results = asyncio.run(run_suite(cases, settings=settings))

    ok = print_report(results)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
