import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is not installed")

RATE, MONTHS = 9.5 / 1200, 60


def emi(loan):
    if loan <= 0:
        return 0.0
    f = (1 + RATE) ** MONTHS
    return loan * RATE * f / (f - 1)


def js_costs(cases):
    script = (
        "const o=require(process.argv[1]);"
        "const cases=JSON.parse(process.argv[2]);"
        "process.stdout.write(JSON.stringify(cases.map(c=>o.ownershipCost(c.car,c.km,c.down))));"
    )
    out = subprocess.check_output(["node", "-e", script, str(ROOT / "frontend" / "ownership.js"), json.dumps(cases)])
    return json.loads(out)


CAR = {"price": 1000000, "cost_per_km": 5.0, "service_cost": 8000}


def test_matches_reference_formula():
    (r,) = js_costs([{"car": CAR, "km": 40, "down": 300000}])
    fuel = 40 * 365 / 12 * 5.0
    assert r["down"] == 300000 and r["loan"] == 700000
    assert r["emi"] == pytest.approx(emi(700000), rel=1e-9)
    assert r["fuelMonthly"] == pytest.approx(fuel, rel=1e-9)
    assert r["service"] == 8000
    assert r["total"] == pytest.approx(300000 + emi(700000) * 60 + fuel * 60 + 8000 * 5, rel=1e-9)


def test_blank_down_payment_defaults_to_twenty_percent():
    blank, none, explicit = js_costs([{"car": CAR, "km": 30, "down": None}, {"car": CAR, "km": 30, "down": ""}, {"car": CAR, "km": 30, "down": 200000}])
    assert blank["down"] == 200000 == none["down"]
    assert blank["total"] == pytest.approx(explicit["total"])


def test_down_payment_larger_than_price_means_no_loan():
    (r,) = js_costs([{"car": CAR, "km": 30, "down": 5000000}])
    assert r["down"] == CAR["price"] and r["loan"] == 0 and r["emi"] == 0 and r["hasLoan"] is False
    assert r["total"] == pytest.approx(CAR["price"] + r["fuelMonthly"] * 60 + 8000 * 5)


def test_zero_down_payment_is_respected():
    (r,) = js_costs([{"car": CAR, "km": 30, "down": 0}])
    assert r["down"] == 0 and r["loan"] == CAR["price"]


def test_more_driving_and_less_down_payment_cost_more():
    low, high, small_down, big_down = js_costs([
        {"car": CAR, "km": 10, "down": 200000}, {"car": CAR, "km": 90, "down": 200000},
        {"car": CAR, "km": 30, "down": 100000}, {"car": CAR, "km": 30, "down": 600000},
    ])
    assert high["total"] > low["total"]
    assert small_down["emi"] > big_down["emi"]
    assert small_down["total"] > big_down["total"]


@pytest.mark.parametrize("km", [0, -5, 501, None, "abc"])
def test_invalid_distance_gives_no_result(km):
    assert js_costs([{"car": CAR, "km": km, "down": None}]) == [None]


def test_negative_down_payment_gives_no_result():
    assert js_costs([{"car": CAR, "km": 30, "down": -1}]) == [None]


def test_every_listing_has_sensible_ownership_cost():
    import pandas as pd
    df = pd.read_csv(ROOT / "data" / "cars_india.csv")
    cases = [{"car": {"price": r.Price, "cost_per_km": r.Cost_Per_Km, "service_cost": r.Service_Cost}, "km": 35, "down": None} for r in df.itertuples()]
    results = js_costs(cases)
    assert all(r is not None for r in results)
    for r, price in zip(results, df.Price):
        assert r["emi"] > 0 and r["fuelMonthly"] > 0 and r["service"] > 0
        assert r["interest"] > 0
        assert r["total"] > price * 0.2 + r["interest"]


def test_site_wires_in_ownership_and_founder_page():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert '<script src="ownership.js"></script>' in html
    for needle in ('id="kmInput"', 'id="downInput"', "How many km do you drive per day?", 'id="founder"', 'href="#founder"',
                   "https://www.linkedin.com/in/pranav-ranjan-37b66a324/"):
        assert needle in html, needle
    assert html.index("ownership.js") < html.index("script.js")


def test_single_file_demo_is_up_to_date():
    demo = (ROOT / "automind-demo.html").read_text(encoding="utf-8")
    for name in ("ownership.js", "script.js", "style.css"):
        text = (ROOT / "frontend" / name).read_text(encoding="utf-8")
        assert text in demo, f"automind-demo.html is stale - run python tools/build_demo.py ({name} differs)"
    assert 'id="founder"' in demo and "<script src=" not in demo.replace('src="https', "")


def test_vercel_config_serves_frontend_as_static_site():
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert cfg["framework"] is None and cfg["outputDirectory"] == "frontend" and not cfg["buildCommand"]
    assert (ROOT / "frontend" / "index.html").exists()
