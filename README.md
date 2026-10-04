# AutoMind AI – Car Recommendation for India

Describe the car you want in plain English – *"luxury SUV under 1 crore"*, *"7 seater automatic, no diesel"*, *"cheapest electric car"*,
*"gaadi chahiye 5 seater automatic 8 lakh tak"* – and get ranked matches with the reasons behind each one.

* **191 models · 30 brands · 1,092 listings** – mass market (Alto → Fortuner), EVs and hybrids, and every luxury / supercar brand sold in India
  (Mercedes-Benz, BMW, Audi, Volvo, Jaguar, Land Rover, Lexus, Porsche, Rolls-Royce, Bentley, Lamborghini, Ferrari, Maserati, Aston Martin …).
* **Understands real language** – typos (`luxry sedn`), Hinglish (`sasti gaadi`, `8 lakh tak`), negations (`no diesel`, `avoid tata`), ranges
  (`10 to 14 lakh`, `around 12 lakh`), superlatives (`most expensive`, `fastest`, `best mileage`), countries (`german luxury`, `korean suv`),
  situations (`2 kids, grandparents and a dog`, `6'5 tall`, `impress clients`, `zero petrol expenses`, `ola/uber taxi`).
* **Subjective wishes are handled honestly** – *ladies type car* → easy-to-drive automatic hatchbacks; *stylish*, *big tyres*, *good sound system* → sensible
  proxies (SUVs/coupes, premium models); *colour* and *owner ratings* aren't in the data, so the app says so ("Not in data") instead of faking it.
* **Everyday situations, not just specs** – *"I don't want Tata or Mahindra"* (whole lists of brands), *"most spacious with lowest maintenance"* (several superlatives at once),
  *"billionaire level car"* (ultra-luxury tier: Rolls-Royce, Bentley, Ferrari ...), *"my parents are old, easy to enter"* (tall MPVs/SUVs, automatic), *"my wife is scared of driving"*
  (light automatic hatchbacks, no big engines), *"off-road in the mountains"* (real off-roaders: Thar, Jimny, Bolero, Scorpio, Defender ...), *"taxi for Ola/Uber"* (sedans and MPVs).
* **Conversation, not just search** – after the results, say *cheaper*, *only automatic*, *no diesel*, *bigger*, *more mileage*, *actually petrol*, *remove budget*
  or *start over*. The app remembers what it understood and changes only that (`POST /recommend` takes `previous` + `reference_price`), then tells you what changed.
* **Compare side by side** – add up to 3 cars (any variant) from the results; the table highlights the best value per row and sums it up ("Lowest price: …").
  Your selection survives refining the search.
* **Every requirement is a hard filter.** If nothing satisfies all of them, the least important are relaxed one by one and the UI says which.
* Works **with or without the server** – the same engine is mirrored in JavaScript, so the single-file demo runs on any static host.
* Optional: set `ANTHROPIC_API_KEY` and Claude reads the request first (falls back to the built-in parser on any error).

## Run

```bash
pip install -r requirements.txt
python build_dataset.py            # (re)generates data/cars_india.csv and frontend/cars-data.js
uvicorn main:app --reload          # open http://127.0.0.1:8000
```
No server? Open `automind-demo.html` (self-contained). Rebuild it after any frontend change with `python tools/build_demo.py`.

## How it works

```
text ──> nlu.py ─────────────> preferences ──> recommender.py ──> ranked cars + reasons
         typo fix, brands,      (budget, fuel,    1. hard filters (relax least-important first)
         aliases, extremes,      seats, tier,     2. weighted nearest-neighbour on 5 features
         money / seats / mileage priorities…)        price · running cost per km · power · service cost · seats
                                                  3. best listing per model, brand mix, up to 4 variants, plain-English reasons
```

* **Ideal-car matching** – the request becomes a target point (e.g. 85 % of the budget, top-quartile power for "fast"); listings are ranked by
  weighted distance in a standardised, log-scaled space, so a Rs 5 lakh and a Rs 5 crore car are compared by ratio, not raw rupees.
* **Efficiency is cost per km** (₹/km) so petrol, diesel, CNG, hybrid and electric cars are comparable; km/l and EV range are shown on the cards.
* **Superlatives** (`most expensive`, `cheapest`, `fastest`, `best mileage`, `biggest`, `lowest maintenance`) rank strictly by that quality
  within everything else the user asked for (e.g. *most expensive SUV under 2 crore*).
* **Mainstream by default** – with no hint of luxury, results stay in the mass market; say *luxury*, *premium*, a brand, or a big budget to go up.
* **Unrecognised input** (`batmobile`) is reported honestly instead of pretending to understand.

## Data

`build_dataset.py` holds a hand-curated catalogue of real Indian-market models (engine, fuel, gearbox, seats, efficiency, power) with
**approximate 2025 ex-showroom price bands** expanded into base / mid / top trims. Prices and model line-ups change often – treat them as indicative
and edit the catalogue to update. (The first version of this project used randomly generated data, which is why a Kwid could cost Rs 35 lakh.)

Two hand-curated flags in the catalogue back the last features: `OFFROAD_MODELS` (body-on-frame / 4x4-capable models, so crossovers like Creta or Seltos don't count)
and the ultra-luxury tier (models typically above ₹2.5 crore). Without a budget, off-road searches stay in the mainstream range (Thar, Jimny, Bolero ...);
say *luxury*, *money is no issue* or a bigger budget to get Defender, G-Class, Range Rover and friends.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```
203 tests: data realism, *every returned car respects every stated requirement* for ~120 realistic and deliberately odd queries, the originally
reported bugs, every brand searchable, and a **parity test** that runs the same queries through the Python and the browser engine and requires identical results
(needs Node.js; skipped if absent).

## Project layout

| Path | Purpose |
|---|---|
| `main.py` | FastAPI app (`POST /recommend`, `GET /api/health`) + serves the website |
| `nlu.py` | Text → preferences; `refine()` applies follow-ups to the previous search |
| `recommender.py` | Filtering, ranking, explanations |
| `llm.py` | Optional Claude-based request reader |
| `build_dataset.py` | Catalogue → CSV + browser data + parser vocabulary |
| `frontend/` | Website (`engine.js` = browser copy of the engine) |
| `frontend/ownership.js` | EMI, fuel / electricity, service and 5-year total calculator (shared by the UI and the tests) |
| `tools/build_demo.py` | Builds the single-file `automind-demo.html` |
| `download_photos.py` | Optional: fetch car photos from Wikipedia into `car_images/` |
| `tests/` | pytest suite |

## Limitations

Prices are indicative; no used-car market; photos load from Wikipedia at view time unless added to `car_images/`; the parser is rule-based,
so very unusual phrasings may be missed (enable the Claude option for those).

## Guided 10-Question Car Finder

The frontend now supports two recommendation modes:

1. **Describe your ideal car** — the original natural-language search.
2. **Help me choose** — a guided 10-question questionnaire that converts the user's answers into a natural-language preference query and sends it through the same recommendation engine.

### Quick demo

- **Windows:** double-click `LIVE_DEMO.bat`.
- **Mac/Linux:** run `./LIVE_DEMO.sh`, then open `http://localhost:8080/frontend/index.html`.
- The frontend also contains the browser-side recommendation engine, so the questionnaire can demonstrate recommendations without the FastAPI backend.

## Ownership cost with EMI

Under the results there is one question, **How many km do you drive per day?**, plus an optional **Down payment** (in ₹ lakh; blank means 20% of the price).
Every car and variant then shows:

* **Monthly EMI**: 5-year car loan at 9.5% on the price minus the down payment (shows "No loan" if the down payment covers the price)
* **Fuel or electricity per month**: km per day x 365/12 x the car's running cost per km
* **Service per year**
* **Total 5-year cost**: down payment + all EMIs + fuel or electricity + 5 years of servicing, as one number

Insurance, road tax and resale value are not included. The compare table gets matching rows (EMI, fuel per month, 5-year total) with the cheapest highlighted.
The loan rate, tenure and default down payment are constants at the top of `frontend/ownership.js`.

## Founder page

Open `#founder` (the **Founder** link in the navbar) for the builder profile. It is part of the same page, so it also works inside the single-file demo and on any static host.

## Guided questionnaire fixes

* "1-2 people" no longer returns only two-seat supercars, and "6 or more people" maps to 7 seats (the data has no 8-seaters).
* Budget bands such as 8-12 lakh now keep their lower limit.
* Business use, comfort and style answers now reach the engine; answers it has no data for (safety ratings, ADAS, sunroof ...) are named in a short note instead of being silently ignored.

## Deploy on Vercel

The website runs fully in the browser (`frontend/engine.js`), so Vercel only needs to host the `frontend/` folder as a static site. `vercel.json` already says so:
no framework, no install, no build, output directory `frontend`. The Python backend (`main.py`, pandas, scikit-learn) is not deployed, which is what
made Vercel fail when it tried to build it as a FastAPI function. If you set things in the dashboard instead: Framework Preset **Other**, Build Command empty,
Output Directory **frontend**. To run the full FastAPI version, host it on Render or Railway with `uvicorn main:app --host 0.0.0.0 --port $PORT`.
