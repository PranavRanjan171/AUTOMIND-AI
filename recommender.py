"""Recommendation engine: hard filters first, then a weighted nearest-neighbour ranking on what is left.

Pipeline for one request (preferences come from nlu.py or from the optional LLM parser):
  1. Hard filters   - every constraint the user stated (budget, fuel, seats, brand, luxury tier ...).  If nothing satisfies all of
                      them, the least important ones are relaxed one by one and the user is told which.
  2. Ranking        - each listing is compared with an "ideal car" built from the request, in a standardised 5-dimensional
                      space (price, running cost per km, power, service cost, seats) with weights chosen from the user's
                      priorities.  Smaller distance = better match.  "Most expensive / cheapest / fastest ..." requests skip
                      the ideal-car idea and rank strictly by that one quality.
  3. Presentation   - best listing per model, a mix of brands, up to four fuel/gearbox variants per model, and plain-English reasons.
"""
import math

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from nlu import inr, money

LATEST_YEAR = 2025
FEATURES = ["Price", "Cost_Per_Km", "Power_bhp", "Service_Cost", "Seating_Capacity"]
LOG = {"Price", "Cost_Per_Km", "Power_bhp", "Service_Cost"}       # heavy-tailed (Alto K10 .. Rolls-Royce): compare ratios, not rupees
PREFER_PENALTY = 0.12     # added when a body type is merely preferred over the other acceptable ones
SOFT_PENALTY = 0.35        # added to the distance when a "nice to have" (e.g. suits city driving) is not met
RECENCY_PENALTY = 0.03     # per model-year older than the newest
SCORE_SHARPNESS = 1.2      # distance -> 0..100 match score: 100 * exp(-SHARPNESS * distance)
MAX_PER_BRAND = 2          # keeps a broad request from returning five cars of the same brand

EXTREME_METRIC = {"price_desc": ("Price", "max"), "price_asc": ("Price", "min"), "mileage_desc": ("Mileage", "max"),
                  "power_desc": ("Power_bhp", "max"), "seats_desc": ("Seating_Capacity", "max"), "service_asc": ("Service_Cost", "min")}
EXTREME_REASON = {"price_desc": "Among the most expensive matches", "price_asc": "Among the lowest-priced matches",
                  "mileage_desc": "Top mileage in this search", "power_desc": "Most powerful in this search",
                  "seats_desc": "Most seating in this search", "service_asc": "Lowest running cost in this search"}
EXTREME_BAR = {"price_desc": "Price fit", "price_asc": "Price fit", "mileage_desc": "Efficiency", "power_desc": "Power",
               "seats_desc": "Seating", "service_asc": "Running cost"}


def _t(col, x):
    return np.log10(x) if col in LOG else x


class Recommender:
    def __init__(self, csv_path, images=None):
        self.cars = pd.read_csv(csv_path)
        self.cars["Is_EV"] = self.cars.Fuel_Type == "Electric"
        self.images = images or {}
        z = pd.DataFrame({c: _t(c, self.cars[c]) for c in FEATURES})
        self.scaler = StandardScaler().fit(z)
        self.sd = dict(zip(FEATURES, self.scaler.scale_))
        self.sd["Mileage"] = float(self.cars.Mileage.std(ddof=0))
        self.sd["Range_km"] = float(self.cars.Range_km.std(ddof=0))
        self.body = self.cars.drop_duplicates("Model").set_index("Model").Body_Type.to_dict()

    # ------------------------------------------------------------------ 1. hard filters
    def constraint_masks(self, p, c):
        """(name, preference keys to clear if relaxed, mask) ordered from least to most important."""
        out = []
        if p["ultra"]:      # implied by "billionaire / money is no issue": the first thing to give up if nothing else fits
            out.append(("ultra-luxury tier", ["ultra"], c.Ultra_Luxury == 1))
        if p["min_mileage"]:  # km/l is a fuel-car figure: EVs only count when the user asked for electric
            mk = c.Mileage >= p["min_mileage"]
            out.append(("mileage", ["min_mileage"], (mk | c.Is_EV) if "Electric" in p["fuels"] else mk))
        if p["min_year"]:
            out.append(("year", ["min_year"], c.Year >= p["min_year"]))
        if p["transmission"]:
            out.append(("transmission", ["transmission"], c.Transmission == p["transmission"]))
        if p["offroad"]:
            out.append(("off-road capability", ["offroad"], c.Offroad == 1))
        if p["body"] or p["exclude_bodies"] or p["body_in"]:
            mk = (c.Body_Type == p["body"]) if p["body"] else pd.Series(True, index=c.index)
            if p["body_in"]:
                mk = mk & c.Body_Type.isin(p["body_in"])
            out.append(("body type", ["body", "exclude_bodies", "body_in"], mk & ~c.Body_Type.isin(p["exclude_bodies"])))
        if p["seats"]:
            mk = (c.Seating_Capacity == p["seats"]) if p["seats_exact"] else (c.Seating_Capacity >= p["seats"])
            out.append(("seating", ["seats", "seats_exact"], mk))
        if p["fuels"] or p["exclude_fuels"]:
            mk = c.Fuel_Type.isin(p["fuels"]) if p["fuels"] else pd.Series(True, index=c.index)
            out.append(("fuel type", ["fuels", "exclude_fuels"], mk & ~c.Fuel_Type.isin(p["exclude_fuels"])))
        if p["segment"]:
            out.append(("luxury tier", ["segment"], c.Segment.isin(p["segment"])))
        if p["brands"] or p["exclude_brands"]:
            mk = c.Brand.isin(p["brands"]) if p["brands"] else pd.Series(True, index=c.index)
            out.append(("brand", ["brands", "exclude_brands"], mk & ~c.Brand.isin(p["exclude_brands"])))
        if p["min_budget"]:
            out.append(("minimum price", ["min_budget"], c.Price >= p["min_budget"]))
        if p["budget"]:
            out.append(("budget", ["budget"], c.Price <= p["budget"]))
        return out

    # ------------------------------------------------------------------ 2. ranking
    @staticmethod
    def weights(p):
        asked_seats = bool(p["seats"] or p["seats_target"] or p["similar"])
        if p["performance_priority"]:
            w = [.15, .05, .45, .20, .15]
        elif p["ultra"]:
            w = [.55, .05, .20, .10, .10]       # the very top of the market: it is about the price tier, not running costs
        elif p["offroad"] and not asked_seats:
            w = [.40, .25, .10, .25, .0]        # off-roaders come as 4, 5 and 7 seaters: the seat count says nothing about the fit
        elif p["mileage_priority"]:
            w = [.15, .45, .15, .15, .10]
        elif p["maintenance_priority"]:
            w = [.20, .15, .10, .45, .10]
        elif p["easy_drive"]:
            w = [.30, .20, .25, .15, .10]       # a nervous driver: price matters, and so does NOT having a big engine
        elif p["budget_priority"]:
            w = [.45, .15, .10, .20, .10]
        elif asked_seats:
            w = [.30, .20, .10, .15, .25]
        else:
            w = [.35, .25, .10, .20, .10]       # nothing specific asked: seat count barely matters
        return np.array(w)

    def ideal_car(self, df, p):
        """The target the listings are compared with, plus which direction counts as 'better than asked' per feature."""
        pool = df[df.Segment != "Luxury"] if p.get("mass_market") and (df.Segment != "Luxury").any() else df
        q = lambda col, x: float(pool[col].quantile(x))
        cheap = p["budget_priority"] and not p["performance_priority"]
        luxury_only = bool(p["segment"])
        if p["budget"]:
            price = p["budget"] * (0.6 if cheap else 0.95 if p["premium"] else 0.85)
            if p["min_budget"]:
                price = max(price, p["min_budget"])
        else:
            price = q("Price", 0.05 if cheap else 0.9 if p["ultra"] else (0.5 if luxury_only else 0.7) if p["premium"] else 0.5)
        cost_target = 100.0 / p["min_mileage"] if p["min_mileage"] else q("Cost_Per_Km", 0.15 if p["mileage_priority"] else 0.5)
        target = dict(Price=price, Cost_Per_Km=cost_target,
                      Power_bhp=q("Power_bhp", 0.8 if p["performance_priority"] else 0.25 if p["easy_drive"] else 0.7 if p["premium"] else 0.5),
                      Service_Cost=q("Service_Cost", 0.15 if p["maintenance_priority"] else 0.7 if p["premium"] else 0.5),
                      Seating_Capacity=p["seats"] or p["seats_target"] or q("Seating_Capacity", 0.5))
        side = dict(Price="both",
                    Cost_Per_Km="lower" if p["mileage_priority"] or cheap else "both",
                    Power_bhp="higher" if p["performance_priority"] else "lower" if cheap or p["easy_drive"] else "both",
                    Service_Cost="lower" if p["maintenance_priority"] or cheap else "both",
                    Seating_Capacity="higher" if "MPV" in p["prefer_body"] else "both")   # elders: roomy MPVs are welcome, extra seats are no drawback
        if p["similar"]:  # "like a Creta": aim for that model's typical specs for everything not asked for explicitly
            ref = self.cars[self.cars.Model == p["similar"]]
            keep = dict(Price=p["budget"] or p["budget_priority"] or p["premium"], Cost_Per_Km=p["min_mileage"] or p["mileage_priority"],
                        Power_bhp=p["performance_priority"], Service_Cost=p["maintenance_priority"],
                        Seating_Capacity=p["seats"] or p["seats_target"])
            for col in FEATURES:
                if not keep[col]:
                    target[col], side[col] = float(ref[col].median()), "both"
        return target, side

    def _features(self, df, target, side):
        """Standardised feature matrix; values already better than the target are pulled onto it (no penalty for 'too good')."""
        z = {}
        for col in FEATURES:
            x, goal = _t(col, df[col].to_numpy(float)), _t(col, target[col])
            if side[col] == "lower":
                x = np.maximum(x, goal)
            elif side[col] == "higher":
                x = np.minimum(x, goal)
            z[col] = x
        goal = pd.DataFrame({c: [_t(c, target[c])] for c in FEATURES})
        return self.scaler.transform(pd.DataFrame(z, index=df.index)), self.scaler.transform(goal)

    def balanced_distance(self, df, p):
        target, side = self.ideal_car(df, p)
        X, g = self._features(df, target, side)
        w = np.sqrt(self.weights(p))
        nn = NearestNeighbors(n_neighbors=len(df), algorithm="brute").fit(X * w)
        dist, idx = nn.kneighbors(g * w)
        d = np.empty(len(df))
        d[idx[0]] = dist[0]
        return d, target, side

    def rank(self, df, p):
        d, target, side = self.balanced_distance(df, p)
        metric = None
        if p["extreme"]:
            gap_total = np.zeros(len(df))
            for name in [p["extreme"]] + p["extreme_more"]:   # "most spacious with lowest maintenance": every quality counts
                col, how = EXTREME_METRIC[name]
                if col == "Mileage" and (p["fuels"] == ["Electric"] or df.Mileage.isna().all()):
                    col = "Range_km"                           # electric-only search: "best mileage" means longest range
                vals = df[col].to_numpy(float)
                best = np.nanmax(vals) if how == "max" else np.nanmin(vals)
                gap_total += np.nan_to_num(np.abs(_t(col, vals) - _t(col, best)) / self.sd.get(col, 1.0), nan=5.0)   # mixed EV/fuel search: EVs have no km/l
                metric = metric or (col, best)
            d = gap_total + 0.03 * d                           # the qualities decide; the balanced distance only breaks ties
        out = df.copy()
        d = d.copy()
        if p["soft_body"]:
            d += SOFT_PENALTY * (~out.Body_Type.isin(p["soft_body"])).to_numpy()
        if p["prefer_body"]:
            d += PREFER_PENALTY * (~out.Body_Type.isin(p["prefer_body"])).to_numpy()
        if p["soft_fuel"]:
            d += SOFT_PENALTY * (~out.Fuel_Type.isin(p["soft_fuel"])).to_numpy()
        if p["soft_segment"]:
            d += SOFT_PENALTY * (~out.Segment.isin(p["soft_segment"])).to_numpy()
        if p["soft_transmission"]:
            d += SOFT_PENALTY * (out.Transmission != p["soft_transmission"]).to_numpy()
        if not p["extreme"]:
            d += RECENCY_PENALTY * (LATEST_YEAR - out.Year.to_numpy())
        if p["similar"]:                                   # the model the user named always leads its own look-alikes
            named = out.Model.to_numpy() == p["similar"]
            if named.any() and (~named).any():
                d = np.where(named, np.minimum(d * 0.25, d[~named].min() * 0.9), d)
        out["score"] = 100 * np.exp(-SCORE_SHARPNESS * d)
        out["_pos"] = np.arange(len(out))
        out = out.sort_values(["score", "_pos"], ascending=[False, True], kind="stable")
        return out, target, side, metric

    # ------------------------------------------------------------------ 3. presentation
    def explain(self, car, p, df):
        ev = bool(car.Is_EV)
        good, warn = [], []
        for name in ([p["extreme"]] + p["extreme_more"]) if p["extreme"] else []:
            good.append(EXTREME_REASON[name])
        if p["ultra"]:
            (good if car.Ultra_Luxury else warn).append("Ultra-luxury tier" if car.Ultra_Luxury else "Not in the ultra-luxury tier")
        if p["offroad"]:
            (good if car.Offroad else warn).append("Built for off-road use" if car.Offroad else "Not a dedicated off-roader")
        if p["body_in"]:
            (good if car.Body_Type in p["body_in"] else warn).append(f"{car.Body_Type} - the usual choice for fleets" if car.Body_Type in p["body_in"] else car.Body_Type)
        if p["soft_transmission"] and car.Transmission == p["soft_transmission"]:
            good.append(f"{car.Transmission} - easy to drive")
        if p["similar"] and car.Model == p["similar"]:
            good.append("The model you asked about")
        elif p["similar"]:
            good.append(f"Similar to the {p['similar']}")
        if p["brands"]:
            (good if car.Brand in p["brands"] else warn).append(car.Brand if car.Brand in p["brands"] else f"{car.Brand}, not {'/'.join(p['brands'])}")
        if p["segment"]:
            (good if car.Segment in p["segment"] else warn).append("Luxury segment" if car.Segment in p["segment"] else "Not a luxury model")
        if p["budget"]:
            spare = p["budget"] - car.Price
            if spare < 0:
                warn.append("Above your budget")
            else:
                good.append(f"{money(spare)} under budget" if spare >= 5e4 else "Within your budget")
        elif p["min_budget"]:
            (good if car.Price >= p["min_budget"] else warn).append(f"Priced at {money(car.Price)}")
        if p["fuels"]:
            (good if car.Fuel_Type in p["fuels"] else warn).append(f"{car.Fuel_Type} as requested" if car.Fuel_Type in p["fuels"] else f"{car.Fuel_Type}, not {'/'.join(p['fuels'])}")
        if car.Fuel_Type in p["exclude_fuels"]:
            warn.append(f"{car.Fuel_Type} (you wanted to avoid it)")
        if p["transmission"]:
            (good if car.Transmission == p["transmission"] else warn).append(f"{car.Transmission} gearbox")
        if p["body"]:
            (good if car.Body_Type == p["body"] else warn).append(car.Body_Type if car.Body_Type == p["body"] else f"{car.Body_Type}, not {p['body']}")
        if p["seats"]:
            ok = car.Seating_Capacity == p["seats"] if p["seats_exact"] else car.Seating_Capacity >= p["seats"]
            (good if ok else warn).append(f"{car.Seating_Capacity} seats")
        if p["min_year"]:
            (good if car.Year >= p["min_year"] else warn).append(f"{int(car.Year)} model")
        if p["use"] and p["soft_body"] and car.Body_Type in p["soft_body"]:
            good.append(f"Suits {p['use']}")
        if p["mileage_priority"] and not p["extreme"]:
            if ev:
                good.append(f"Electric - about ₹{car.Cost_Per_Km:.1f}/km to run")
            elif car.Cost_Per_Km <= df.Cost_Per_Km.median():
                good.append(f"Good mileage: {car.Mileage:g} km/l")
        if p["min_mileage"] and not ev and car.Mileage < p["min_mileage"]:
            warn.append(f"Only {car.Mileage:g} km/l")
        if p["performance_priority"] and not p["extreme"] and car.Power_bhp >= df.Power_bhp.quantile(0.6):
            good.append(f"Strong {int(car.Power_bhp)} bhp")
        if p["maintenance_priority"] and not p["extreme"] and car.Service_Cost <= df.Service_Cost.quantile(0.4):
            good.append(f"Low service cost (₹{inr(car.Service_Cost)})")
        if p["premium"] and not p["extreme"] and not p["segment"] and car.Price >= df.Price.quantile(0.7):
            good.append("Premium pricing tier")
        return (good or ["Well-balanced overall match"]), warn

    def recommend(self, p, top_n=5):
        cars = self.cars
        masks = self.constraint_masks(p, cars)
        dropped, df = [], cars
        for k in range(len(masks) + 1):
            dropped = masks[:k]
            keep = [m[2] for m in masks[k:]]
            df = cars[np.logical_and.reduce(keep)] if keep else cars
            if len(df):
                break
        if "mileage_desc" in ([p["extreme"]] + p["extreme_more"]) and "Electric" not in p["fuels"] and (~df.Is_EV).any():
            df = df[~df.Is_EV]                            # km/l has no meaning for an EV; ask for "electric" to rank by range

        used = dict(p)
        for _, keys, _ in dropped:  # ignore relaxed constraints when scoring, but still flag them on each card
            for key in keys:
                used[key] = [] if isinstance(p[key], list) else (False if isinstance(p[key], bool) else None)
        # Nothing hinting at luxury (no brand, tier, budget above Rs 50 lakh, "premium" ...): default to the mainstream market
        # so that "automatic city car" is not answered with a Rs 60 lakh sedan just because the catalogue includes them.
        used["mass_market"] = not (p["premium"] or p["segment"] or p["soft_segment"] or p["brands"] or p["similar"] or p["extreme"]
                                   or p["min_budget"] or (p["budget"] and p["budget"] > 50e5))
        if used["mass_market"]:
            used["soft_segment"] = ["Budget", "Mainstream", "Premium"]
        ranked, target, side, metric = self.rank(df, used)

        def fit(col, x):
            x, goal = _t(col, float(x)), _t(col, target[col])
            if (side[col] == "lower" and x < goal) or (side[col] == "higher" and x > goal):
                return 100
            return int(math.floor(100 * math.exp(-abs(x - goal) / self.sd[col]) + 0.5))

        def variant(c):
            ev = bool(c.Is_EV)
            reasons, caveats = self.explain(c, p, df)
            bars = [dict(label="Price fit", fit=fit("Price", c.Price)), dict(label="Efficiency", fit=fit("Cost_Per_Km", c.Cost_Per_Km)),
                    dict(label="Power", fit=fit("Power_bhp", c.Power_bhp)), dict(label="Running cost", fit=fit("Service_Cost", c.Service_Cost)),
                    dict(label="Seating", fit=fit("Seating_Capacity", c.Seating_Capacity))]
            if p["extreme"]:
                keep = {EXTREME_BAR[n] for n in [p["extreme"]] + p["extreme_more"]}
                bars = [b for b in bars if b["label"] in keep]
            return dict(
                year=int(c.Year), price=int(c.Price), mileage=None if ev else float(c.Mileage),
                range_km=int(c.Range_km) if ev else None, engine_cc=None if pd.isna(c.Engine_CC) else int(c.Engine_CC),
                power_hp=int(c.Power_bhp), fuel_type=str(c.Fuel_Type), transmission=str(c.Transmission),
                seating_capacity=int(c.Seating_Capacity), service_cost=int(c.Service_Cost), cost_per_km=float(c.Cost_Per_Km),
                recommendation_score=round(float(c.score), 1), reasons=reasons[:5], caveats=caveats, breakdown=bars)

        # best listing per model; a mix of brands unless the user is clearly after one brand / one model / one extreme
        cap = 99 if (p["brands"] or p["similar"] or p["extreme"] or p["offroad"]) else 1 if p["ultra"] else MAX_PER_BRAND   # ultra: one car per marque = a tour of the tier
        picked, per_brand, seen = [], {}, set()
        for _, c in ranked.iterrows():
            key = (c.Brand, c.Model)
            if key in seen or per_brand.get(c.Brand, 0) >= cap:
                continue
            seen.add(key)
            per_brand[c.Brand] = per_brand.get(c.Brand, 0) + 1
            picked.append(c)
            if len(picked) == top_n:
                break
        if len(picked) < top_n:        # too few other brands to honour the mix: fill the rest by rank
            for _, c in ranked.iterrows():
                if (c.Brand, c.Model) not in seen:
                    seen.add((c.Brand, c.Model))
                    picked.append(c)
                    if len(picked) == top_n:
                        break

        recs = []
        for c in picked:
            rows = ranked[(ranked.Brand == c.Brand) & (ranked.Model == c.Model)].drop_duplicates(["Fuel_Type", "Transmission"]).head(4)
            variants = [variant(v) for _, v in rows.iterrows()]   # the repeated rows are real variants of the model
            img = self.images.get(f"{c.Brand}_{c.Model}".replace(" ", "_").lower())
            recs.append(dict(brand=str(c.Brand), model=str(c.Model), body_type=str(c.Body_Type), segment=str(c.Segment),
                             image_url=f"/car-images/{img}" if img else "", **variants[0], variants=variants))
        notice = None
        if dropped:
            notice = "No car matched everything you asked for, so we loosened: " + ", ".join(d[0] for d in dropped) + ". These are the closest matches."
        return dict(notice=notice, relaxed=[d[0] for d in dropped],
                    stats=dict(listings=len(cars), matched=len(df), models=int(df.Model.nunique())), recommendations=recs)
