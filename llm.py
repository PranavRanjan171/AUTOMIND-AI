"""Optional: let Claude read the request when ANTHROPIC_API_KEY is set.  Any problem -> None and the built-in parser is used."""
import json
import logging
import os
import urllib.request

log = logging.getLogger("automind")

FUELS = {"Petrol", "Diesel", "Electric", "CNG", "Hybrid"}
BODIES = {"SUV", "Sedan", "Hatchback", "MPV", "Coupe"}
PRIORITY_KEYS = {"performance": "performance_priority", "mileage": "mileage_priority", "maintenance": "maintenance_priority",
                 "low_price": "budget_priority", "premium": "premium"}
EXTREMES = {"price_desc", "price_asc", "mileage_desc", "power_desc", "seats_desc", "service_asc"}

PROMPT = """You convert a car-shopping request (any wording, any language, typos allowed) into JSON for a search engine.
Reply with ONE JSON object and nothing else. Omit keys you are unsure about. Keys:
budget_max_lakh (number), budget_min_lakh (number), fuels (list of Petrol/Diesel/Electric/CNG/Hybrid), exclude_fuels (same),
transmission (Automatic|Manual), seats_min (integer 2-8), body (SUV|Sedan|Hatchback|MPV|Coupe), exclude_bodies (list),
brands (list of: %s), exclude_brands (same), similar_model (one of: %s), min_mileage (km/l number), min_year (integer),
luxury (true when they want a luxury brand), rank_by (one of: price_desc, price_asc, mileage_desc, power_desc, seats_desc, service_asc
- use when they ask for the most expensive / cheapest / best mileage / fastest / biggest / lowest-maintenance car),
priorities (list from: performance, mileage, maintenance, low_price, premium), best_for (2-3 words)."""


def sanitize(d, brands, models):
    """Keep only well-formed values, translated into the same preference keys the built-in parser uses."""
    if not isinstance(d, dict):
        return {}
    brands, models = set(brands), set(models)
    lst = lambda v, ok: [x for x in v if x in ok] if isinstance(v, list) else []
    num = lambda v: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None
    out = {}
    if num(d.get("budget_max_lakh")):
        out["budget"] = num(d["budget_max_lakh"]) * 1e5
    if num(d.get("budget_min_lakh")):
        out["min_budget"] = num(d["budget_min_lakh"]) * 1e5
    for src, ok in [("fuels", FUELS), ("exclude_fuels", FUELS), ("exclude_bodies", BODIES), ("brands", brands), ("exclude_brands", brands)]:
        if lst(d.get(src), ok):
            out[src] = lst(d.get(src), ok)
    if d.get("transmission") in ("Automatic", "Manual"):
        out["transmission"] = d["transmission"]
    if d.get("body") in BODIES:
        out["body"] = d["body"]
    if d.get("similar_model") in models:
        out["similar"] = d["similar_model"]
    if num(d.get("seats_min")) and 2 <= d["seats_min"] <= 8:
        out["seats"] = int(d["seats_min"])
        out["seats_exact"] = out["seats"] <= 2
    if num(d.get("min_mileage")):
        out["min_mileage"] = num(d["min_mileage"])
    if num(d.get("min_year")) and 2000 <= d["min_year"] <= 2030:
        out["min_year"] = int(d["min_year"])
    if d.get("luxury") is True:
        out["segment"] = ["Luxury"]
    if d.get("rank_by") in EXTREMES:
        out["extreme"] = d["rank_by"]
    for pr in lst(d.get("priorities"), set(PRIORITY_KEYS)):
        out[PRIORITY_KEYS[pr]] = True
    if isinstance(d.get("best_for"), str) and d["best_for"].strip():
        out["use"] = d["best_for"].strip()[:30]
    return out


def llm_preferences(query, brands, models):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        payload = json.dumps({"model": os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"), "max_tokens": 400,
                              "system": PROMPT % (", ".join(sorted(brands)), ", ".join(sorted(models))),
                              "messages": [{"role": "user", "content": query}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", payload, {
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            text = json.load(r)["content"][0]["text"]
        return sanitize(json.loads(text[text.index("{"): text.rindex("}") + 1]), brands, models) or None
    except Exception:
        log.warning("AI understanding unavailable, using built-in parser", exc_info=True)
        return None
