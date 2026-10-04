"""The website falls back to frontend/engine.js when the server is down.  Both engines must give the same answers."""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.queries import CHAINS, QUERIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def python_answers():
    import main
    out = {q: main.recommend_cars(q) for q in QUERIES}
    for chain in CHAINS:
        prev = ref = None
        for i, q in enumerate(chain):
            r = main.recommend_cars(q, prev, ref)
            prev, ref = r["understood_preferences"], r["recommendations"][0]["price"]
            out[" > ".join(chain[: i + 1])] = r
    return out


def js_answers():
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(QUERIES + CHAINS, f)
    out = subprocess.run(["node", str(ROOT / "tests" / "js_dump.js"), f.name], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_python_and_browser_engines_agree():
    py, js = python_answers(), js_answers()
    problems = []
    for q in py:
        a, b = py[q], js[q]
        if a["changes"] != b["changes"]:
            problems.append(f"{q!r}: follow-up changes differ\n   py {a['changes']}\n   js {b['changes']}")
            continue
        if a["summary"] != b["summary"]:
            problems.append(f"{q!r}: understood differently\n   py {a['summary']}\n   js {b['summary']}")
            continue
        pa = [(r["brand"], r["model"], r["fuel_type"], r["transmission"], r["price"]) for r in a["recommendations"]]
        pb = [(r["brand"], r["model"], r["fuel_type"], r["transmission"], r["price"]) for r in b["recommendations"]]
        if pa != pb:
            problems.append(f"{q!r}: different cars\n   py {[x[:2] for x in pa]}\n   js {[x[:2] for x in pb]}")
        elif (a["notice"] or "") != (b["notice"] or "") or a["stats"] != b["stats"]:
            problems.append(f"{q!r}: different notice/stats")
        else:
            for ra, rb in zip(a["recommendations"], b["recommendations"]):
                if abs(ra["recommendation_score"] - rb["recommendation_score"]) > 0.11 or ra["reasons"] != rb["reasons"] or ra["caveats"] != rb["caveats"]:
                    problems.append(f"{q!r}: {ra['brand']} {ra['model']} score/reasons differ: {ra['recommendation_score']} {ra['reasons']} vs {rb['recommendation_score']} {rb['reasons']}")
    assert not problems, "\n".join(problems)
