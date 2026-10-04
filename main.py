"""AutoMind AI - car recommendation API + website.

Run:  uvicorn main:app --reload      then open  http://127.0.0.1:8000
"""
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from llm import llm_preferences
from nlu import Understander, sanitize_prefs, summarise
from recommender import Recommender

BASE = Path(__file__).resolve().parent
log = logging.getLogger("automind")

app = FastAPI(title="AutoMind AI - Car Recommendation API", version="3.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

# ---------------------------------------------------------------- data (run `python build_dataset.py` to regenerate it)
(BASE / "car_images").mkdir(exist_ok=True)
DATA_FILE = BASE / "data" / "cars_india.csv"
LEXICON_FILE = BASE / "data" / "lexicon.json"
for f in (DATA_FILE, LEXICON_FILE):
    if not f.exists():
        raise SystemExit(f"{f} not found - run `python build_dataset.py` first.")

# Real photos placed in car_images/ (named Brand_Model.jpeg) are used; anything else gets a clean placeholder in the browser.
IMAGES = {p.stem.lower(): p.name for p in (BASE / "car_images").glob("*.*") if p.suffix.lower() != ".txt"}
engine = Recommender(DATA_FILE, IMAGES)
cars = engine.cars
MODEL_BRAND = cars.drop_duplicates("Model").set_index("Model").Brand.to_dict()
MODEL_SEGMENT = cars.drop_duplicates("Model").set_index("Model").Segment.to_dict()
understander = Understander(sorted(cars.Model.unique()), MODEL_BRAND, json.loads(LEXICON_FILE.read_text(encoding="utf-8")))


NO_CLUE = "I could not pick out a specific requirement from that, so these are well-rounded popular picks. Try adding a budget, fuel, seats or body type."


class CarRequest(BaseModel):
    query: str = Field(..., max_length=300)
    previous: dict | None = None            # what the last search understood - makes this request a follow-up ("cheaper", "only automatic")
    reference_price: float | None = None    # price of the top car shown, so "cheaper" / "more expensive" have something to compare with


def recommend_cars(query, previous=None, reference_price=None):
    ai = None
    if previous is not None:
        prev = sanitize_prefs(previous, understander.all_brands, understander.models)
        p = understander.refine(prev, query, reference_price)
    else:
        p = understander.extract(query)
        ai = llm_preferences(query, understander.all_brands, understander.models)
        if ai:
            p.update(ai)
    if p["similar"]:  # "like a Creta": prefer the same kind of car (body and market segment)
        if not p["body"] and not p["soft_body"]:
            p["soft_body"] = [engine.body.get(p["similar"], "Other")]
        if not p["segment"] and not p["soft_segment"]:
            p["soft_segment"] = [MODEL_SEGMENT[p["similar"]]]
    result = engine.recommend(p)
    summary = summarise(p)
    if p["notes"]:   # things we understood but have no data for: say so
        result["notice"] = " ".join(filter(None, [result["notice"]] + [x[1] for x in p["notes"]]))
    if not summary and not ai:   # nothing recognisable ("batmobile"): say so instead of pretending to understand
        result["notice"] = NO_CLUE
    changes = []
    if previous is not None:   # what this follow-up changed, for the "Updated: ..." message
        before = summarise(prev)
        changes = [s for s in summary if s not in before]
    return dict(success=True, message="Recommendations generated successfully.", ai=bool(ai), refined=previous is not None,
                changes=changes, summary=summary, understood_preferences=p, **result)


# ---------------------------------------------------------------- routes
@app.get("/api/health")
def health():
    return {"status": "ok", "cars": len(cars), "models": int(cars.Model.nunique()), "brands": int(cars.Brand.nunique())}


@app.post("/recommend")
def recommend(request: CarRequest):
    query = " ".join(request.query.split())
    if not query:
        raise HTTPException(422, "Please describe the car you are looking for.")
    try:
        return recommend_cars(query, request.previous, request.reference_price)
    except Exception:
        log.exception("recommendation failed for %r", request.query)
        raise HTTPException(500, "Something went wrong while finding cars. Please try again.")


app.mount("/car-images", StaticFiles(directory=BASE / "car_images"), name="car_images")
app.mount("/", StaticFiles(directory=BASE / "frontend", html=True), name="frontend")  # keep last


if __name__ == "__main__":  # `python main.py` also works
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
