"""Quality checks: realistic data, every stated requirement is respected, and the originally reported bugs stay fixed."""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402
from tests.queries import QUERIES  # noqa: E402

cars = main.cars
client = TestClient(main.app)
ULTRA_MODELS = set(cars[cars.Ultra_Luxury == 1].Model)
OFFROAD = set(cars[cars.Offroad == 1].Model)
LUXURY = {"Mercedes-Benz", "BMW", "Audi", "Volvo", "Jaguar", "Land Rover", "Lexus", "Porsche", "Rolls-Royce", "Bentley", "Lamborghini", "Ferrari", "Maserati", "Aston Martin"}


# ---------------------------------------------------------------- data
def test_luxury_brands_are_present():
    assert LUXURY <= set(cars.Brand)


def test_prices_are_realistic_per_model():
    spread = cars.groupby("Model").Price.agg(["min", "max"])
    assert ((spread["max"] / spread["min"]) < 2.5).all()          # the old data had a Kwid priced from 2 to 35 lakh
    assert cars[cars.Model.isin(["Alto K10", "Kwid", "Tiago"])].Price.max() < 12e5
    assert cars[cars.Brand.isin(["Rolls-Royce", "Ferrari", "Lamborghini", "Bentley"])].Price.min() > 3e7


def test_specs_are_consistent():
    ev = cars[cars.Fuel_Type == "Electric"]
    assert ev.Engine_CC.isna().all() and ev.Mileage.isna().all() and (ev.Range_km > 100).all()
    assert cars[cars.Fuel_Type != "Electric"].Mileage.between(4, 40).all()
    assert cars.groupby("Model").Seating_Capacity.nunique().max() == 1
    assert cars.groupby("Model").Body_Type.nunique().max() == 1


# ---------------------------------------------------------------- every returned variant respects what was asked
def variants(result):
    return [(r, v) for r in result["recommendations"] for v in r["variants"]]


@pytest.mark.parametrize("query", QUERIES)
def test_hard_requirements_hold(query):
    res = main.recommend_cars(query)
    p, relaxed = res["understood_preferences"], set(res["relaxed"])
    assert res["recommendations"], f"no results for {query!r}"
    for r, v in variants(res):
        if p["budget"] and "budget" not in relaxed:
            assert v["price"] <= p["budget"], (query, r["model"], v["price"])
        if p["min_budget"] and "minimum price" not in relaxed:
            assert v["price"] >= p["min_budget"], (query, r["model"])
        if p["fuels"] and "fuel type" not in relaxed:
            assert v["fuel_type"] in p["fuels"], (query, r["model"], v["fuel_type"])
        if "fuel type" not in relaxed:
            assert v["fuel_type"] not in p["exclude_fuels"]
        if p["transmission"] and "transmission" not in relaxed:
            assert v["transmission"] == p["transmission"], (query, r["model"])
        if p["seats"] and "seating" not in relaxed:
            assert (v["seating_capacity"] == p["seats"]) if p["seats_exact"] else (v["seating_capacity"] >= p["seats"]), (query, r["model"])
        if p["body"] and "body type" not in relaxed:
            assert r["body_type"] == p["body"], (query, r["model"])
        if "body type" not in relaxed:
            assert r["body_type"] not in p["exclude_bodies"]
        if p["brands"] and "brand" not in relaxed:
            assert r["brand"] in p["brands"], (query, r["model"])
        if "brand" not in relaxed:
            assert r["brand"] not in p["exclude_brands"]
        if p["segment"] and "luxury tier" not in relaxed:
            assert r["segment"] == "Luxury", (query, r["model"])
        if p["min_mileage"] and "mileage" not in relaxed and v["fuel_type"] != "Electric":
            assert v["mileage"] >= p["min_mileage"], (query, r["model"])
        if p["body_in"] and "body type" not in relaxed:
            assert r["body_type"] in p["body_in"], (query, r["model"])
        if p["ultra"] and "ultra-luxury tier" not in relaxed:
            assert r["model"] in ULTRA_MODELS, (query, r["model"])
        if p["offroad"] and "off-road capability" not in relaxed:
            assert r["model"] in OFFROAD, (query, r["model"])
        if p["min_year"] and "year" not in relaxed:
            assert v["year"] >= p["min_year"], (query, r["model"])


# ---------------------------------------------------------------- the reported bugs
def test_most_expensive_is_really_the_most_expensive():
    res = main.recommend_cars("most expensive car")
    assert res["recommendations"][0]["price"] == cars.Price.max()
    assert "Verna" not in [r["model"] for r in res["recommendations"]]
    prices = [r["price"] for r in res["recommendations"]]
    assert min(prices) > 9e7                                       # all above Rs 9 crore


def test_other_extremes():
    assert main.recommend_cars("cheapest car")["recommendations"][0]["price"] == cars.Price.min()
    assert main.recommend_cars("fastest car")["recommendations"][0]["power_hp"] == cars.Power_bhp.max()
    assert main.recommend_cars("most expensive SUV under 2 crore")["recommendations"][0]["price"] == cars[(cars.Body_Type == "SUV") & (cars.Price <= 2e7)].Price.max()
    top = main.recommend_cars("best mileage car")["recommendations"][0]
    assert top["mileage"] == cars.Mileage.max()


@pytest.mark.parametrize("word,brand", [("mercedes", "Mercedes-Benz"), ("bmw", "BMW"), ("audi", "Audi"), ("volvo", "Volvo"), ("jaguar", "Jaguar"),
                                        ("land rover", "Land Rover"), ("lexus", "Lexus"), ("porsche", "Porsche"), ("rolls royce", "Rolls-Royce"),
                                        ("bentley", "Bentley"), ("lamborghini", "Lamborghini"), ("ferrari", "Ferrari"), ("maserati", "Maserati"),
                                        ("aston martin", "Aston Martin"), ("tata", "Tata Motors"), ("maruti", "Maruti Suzuki")])
def test_every_brand_is_searchable(word, brand):
    res = main.recommend_cars(word)
    assert res["recommendations"] and all(r["brand"] == brand for r in res["recommendations"])


def test_luxury_query_returns_luxury_brands_from_several_makers():
    res = main.recommend_cars("luxury car")
    assert all(r["brand"] in LUXURY for r in res["recommendations"])
    assert len({r["brand"] for r in res["recommendations"]}) >= 3


def test_named_model_comes_first():
    for name in ["Verna", "Creta", "Fortuner", "Thar", "Swift", "Cullinan", "911"]:
        assert main.recommend_cars(name)["recommendations"][0]["model"] == name


def test_mass_market_requests_do_not_return_luxury():
    for q in ["automatic", "suv", "city traffic automatic", "hybrid", "family car"]:
        assert all(r["segment"] != "Luxury" for r in main.recommend_cars(q)["recommendations"]), q


def test_impossible_request_is_relaxed_and_explained():
    res = main.recommend_cars("7 seater electric under 5 lakh")
    assert res["notice"] and res["recommendations"]


# ---------------------------------------------------------------- API
def test_api():
    assert client.get("/api/health").json()["brands"] == cars.Brand.nunique()
    assert client.post("/recommend", json={"query": "   "}).status_code == 422
    assert client.post("/recommend", json={"query": "x" * 301}).status_code == 422
    body = client.post("/recommend", json={"query": "luxury SUV under 1 crore"}).json()
    assert body["success"] and len(body["recommendations"]) == 5 and body["summary"]
    assert client.get("/").status_code == 200


def test_subjective_requests_are_handled_honestly():
    pink = main.recommend_cars("pink car")
    assert "Colour (pink)" in pink["summary"][0]["value"] and "colour" in pink["notice"].lower()
    assert "Ratings" in main.recommend_cars("good rated car")["summary"][-1]["value"]
    ladies = main.recommend_cars("ladies type car")
    assert all(r["body_type"] == "Hatchback" and r["transmission"] == "Automatic" for r in ladies["recommendations"])
    assert main.recommend_cars("good car")["understood_preferences"]["notes"] == []      # "good" is not the colour "gold"
    assert main.recommend_cars("sedn")["understood_preferences"]["body"] == "Sedan"


# ---------------------------------------------------------------- follow-up conversations
def step(prev, text):
    ref = prev["recommendations"][0]["price"] if prev else None
    return main.recommend_cars(text, prev["understood_preferences"] if prev else None, ref)


def test_cheaper_really_lowers_the_budget_and_keeps_the_rest():
    a = step(None, "7 seater under 20 lakh")
    b = step(a, "cheaper")
    assert b["understood_preferences"]["budget"] < 20e5 and b["understood_preferences"]["seats"] == 7 and b["refined"]
    assert all(v["price"] <= b["understood_preferences"]["budget"] for r in b["recommendations"] for v in r["variants"])
    assert {c["label"] for c in b["changes"]} >= {"Budget"}


def test_follow_ups_accumulate_and_can_be_undone():
    r = step(None, "suv under 15 lakh")
    r = step(r, "only automatic")
    r = step(r, "no diesel")
    p = r["understood_preferences"]
    assert p["transmission"] == "Automatic" and p["exclude_fuels"] == ["Diesel"] and p["body"] == "SUV" and p["budget"] == 15e5
    r = step(r, "actually diesel")
    assert r["understood_preferences"]["fuels"] == ["Diesel"] and r["understood_preferences"]["exclude_fuels"] == []
    r = step(r, "remove budget")
    assert r["understood_preferences"]["budget"] is None and r["understood_preferences"]["body"] == "SUV"
    r = step(r, "start over")
    assert r["understood_preferences"]["body"] is None and not r["summary"]


def test_more_expensive_steps_up_and_cheaper_steps_down_from_the_extreme():
    a = step(None, "5 seater under 10 lakh")
    b = step(a, "more expensive")
    assert min(v["price"] for r in b["recommendations"] for v in r["variants"]) > a["recommendations"][0]["price"]
    c = step(step(None, "most expensive car"), "cheaper")
    assert c["understood_preferences"]["extreme"] is None and c["recommendations"][0]["price"] < 6e7


def test_previous_preferences_from_the_browser_are_validated():
    junk = {"budget": "lots", "fuels": ["Plutonium", 5], "brands": ["<script>"], "similar": "Batmobile", "extreme": "x", "seats": 99, "transmission": "CVT"}
    res = main.recommend_cars("automatic", junk, None)
    p = res["understood_preferences"]
    assert p["budget"] is None and p["fuels"] == [] and p["brands"] == [] and p["similar"] is None and p["seats"] is None and p["transmission"] == "Automatic"
    assert client.post("/recommend", json={"query": "cheaper", "previous": "oops"}).status_code == 422


def test_follow_up_through_the_api():
    first = client.post("/recommend", json={"query": "diesel suv under 20 lakh"}).json()
    second = client.post("/recommend", json={"query": "only automatic", "previous": first["understood_preferences"],
                                              "reference_price": first["recommendations"][0]["price"]}).json()
    assert second["refined"] and second["understood_preferences"]["fuels"] == ["Diesel"] and second["understood_preferences"]["transmission"] == "Automatic"


# ---------------------------------------------------------------- the six reported bugs
def models(res):
    return [r["model"] for r in res["recommendations"]]


@pytest.mark.parametrize("query,excluded", [
    ("I don't want Tata or Mahindra, petrol SUV around 12 lakh", {"Tata Motors", "Mahindra"}),
    ("avoid tata and mahindra and maruti", {"Tata Motors", "Mahindra", "Maruti Suzuki"}),
    ("not interested in maruti or hyundai", {"Maruti Suzuki", "Hyundai"}),
    ("no german cars under 1 crore", {"Mercedes-Benz", "BMW", "Audi", "Porsche", "Volkswagen"}),
])
def test_a_negated_list_excludes_every_brand_in_it(query, excluded):
    res = main.recommend_cars(query)
    p = res["understood_preferences"]
    assert p["brands"] == [] and excluded <= set(p["exclude_brands"])
    assert res["recommendations"] and not {r["brand"] for r in res["recommendations"]} & excluded


def test_negation_keeps_the_things_you_do_want():
    res = main.recommend_cars("I don't want Tata or Mahindra, petrol SUV around 12 lakh")
    assert all(r["body_type"] == "SUV" and v["fuel_type"] == "Petrol" and 10.2e5 <= v["price"] <= 13.8e5 for r, v in variants(res))
    p = main.recommend_cars("no diesel, automatic")["understood_preferences"]
    assert p["exclude_fuels"] == ["Diesel"] and p["transmission"] == "Automatic"          # "," ends the negation
    p = main.recommend_cars("don't want manual or diesel")["understood_preferences"]
    assert p["exclude_fuels"] == ["Diesel"] and p["transmission"] == "Automatic"          # "or" continues it
    p = main.recommend_cars("no diesel and automatic")["understood_preferences"]
    assert p["exclude_fuels"] == ["Diesel"] and p["transmission"] == "Automatic"


def test_two_superlatives_are_both_honoured():
    res = main.recommend_cars("Most spacious car with lowest maintenance")
    assert res["understood_preferences"]["extreme"] == "seats_desc" and res["understood_preferences"]["extreme_more"] == ["service_asc"]
    assert "Most seats + Lowest running cost" in [s["value"] for s in res["summary"]]
    assert all(r["seating_capacity"] == 7 and r["fuel_type"] != "Electric" for r in res["recommendations"])      # not Punch EV / Comet
    cheap_fast = main.recommend_cars("fastest and cheapest car")["understood_preferences"]
    assert {cheap_fast["extreme"], *cheap_fast["extreme_more"]} == {"power_desc", "price_asc"}


def test_billionaire_means_the_ultra_luxury_tier():
    for q in ["Billionaire level car, money is no issue", "ultra luxury suv", "cost no object"]:
        res = main.recommend_cars(q)
        assert res["understood_preferences"]["ultra"] and all(r["model"] in ULTRA_MODELS and r["price"] > 2.5e7 for r in res["recommendations"]), q
    brands = [r["brand"] for r in main.recommend_cars("Billionaire level car, money is no issue")["recommendations"]]
    assert {"Rolls-Royce", "Bentley", "Ferrari"} <= set(brands) and len(set(brands)) == len(brands)     # a tour of the tier, not five of one marque
    assert not {"3 Series Gran Limousine", "Camry", "GLA"} & set(models(main.recommend_cars("Billionaire level car, money is no issue")))


def test_ultra_is_given_up_before_explicit_requirements():
    res = main.recommend_cars("money is no issue, 7 seater under 20 lakh")
    assert "ultra-luxury tier" in res["relaxed"] and all(v["price"] <= 20e5 and r["seating_capacity"] >= 7 for r, v in variants(res))


def test_elderly_passengers_get_tall_easy_entry_cars():
    res = main.recommend_cars("My parents are old, easy to enter car")
    assert all(r["body_type"] in ("SUV", "MPV") for r in res["recommendations"])
    assert sum(r["body_type"] == "MPV" for r in res["recommendations"]) >= 2
    assert all(r["transmission"] == "Automatic" for r in res["recommendations"]) and "Seat height" in res["summary"][-1]["value"]


def test_nervous_driver_gets_easy_automatic_cars_without_big_engines():
    res = main.recommend_cars("my wife is scared of driving, no gear")
    assert all(r["transmission"] == "Automatic" and r["power_hp"] <= 120 for r in res["recommendations"])
    assert sum(r["body_type"] == "Hatchback" for r in res["recommendations"]) >= 2
    assert main.recommend_cars("my wife is scared of driving, no gear")["understood_preferences"]["easy_drive"]


def test_off_road_means_real_off_roaders():
    res = main.recommend_cars("off-road in the mountains")
    assert all(m in OFFROAD for m in models(res))
    assert {"Thar", "Jimny"} <= set(models(res)) and not {"Creta", "Seltos", "Harrier"} & set(models(res))
    assert models(main.recommend_cars("off-road under 15 lakh"))[0] in ("Jimny", "Thar")
    assert {"Defender", "G-Class"} & set(models(main.recommend_cars("luxury off-road suv money is no issue")))


def test_taxis_are_sedans_and_mpvs():
    for q in ["Taxi for Ola/Uber", "taxi under 10 lakh", "cab for fleet, CNG"]:
        res = main.recommend_cars(q)
        assert all(r["body_type"] in ("Sedan", "MPV") for r in res["recommendations"]), q
    assert "Dzire" in models(main.recommend_cars("Taxi for Ola/Uber"))
    assert not {"Sonet", "Nexon", "Altroz"} & set(models(main.recommend_cars("Taxi for Ola/Uber")))
