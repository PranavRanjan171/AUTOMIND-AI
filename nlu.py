"""Natural-language understanding for car searches (typo-tolerant, no external services).

`Understander.extract(text)` turns free text such as
    "luxury SUV under 1 crore, no diesel"  /  "cheapest electric car"  /  "like a Creta but automatic"
into a preferences dict that the recommender understands.  A line-by-line copy of this logic lives in
frontend/engine.js so the website still works when the server is down; tests/test_parity.py keeps both in sync.
"""
import copy
import math
import re

NUM = r"(\d+(?:\.\d+)?)"
UNIT = r"(crore|crores|cr|lakh|lakhs|lac|lacs|l)\b"
WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
FUEL_WORDS = {"petrol": "Petrol", "gasoline": "Petrol", "diesel": "Diesel", "electric": "Electric", "ev": "Electric", "evs": "Electric",
              "cng": "CNG", "hybrid": "Hybrid", "hybrids": "Hybrid"}
BODY_WORDS = {"suv": "SUV", "suvs": "SUV", "sedan": "Sedan", "sedans": "Sedan", "hatchback": "Hatchback", "hatchbacks": "Hatchback",
              "hatch": "Hatchback", "mpv": "MPV", "muv": "MPV", "minivan": "MPV", "coupe": "Coupe", "coupes": "Coupe"}
KEYWORDS = """petrol diesel electric cng gasoline hybrid automatic manual mileage maintenance service seater seats family cheap
affordable budget lakh lakhs crore under below above around about between premium luxury spacious compact small sedan
hatchback suv mpv muv minivan coupe supercar performance powerful sporty speed fast quick pickup average efficient economical
economy comfortable commute daily traffic highway adventure offroad taxi commercial latest newest without avoid people persons
passengers kmpl approximately roughly minimum maximum acceleration beginner learner student office parking kids children
parents expensive costliest priciest cheapest fastest quickest biggest largest luxurious
audio sound system speakers stereo music stylish sleek rated rating ratings reviews review colour color colours colors paint pink red blue white black grey gray silver yellow orange purple brown golden gold maroon beige ladies women woman female wheels tyres tyre alloy""".split()
STOP = {"which", "where", "would", "could", "should", "their", "there", "about", "these", "those", "years", "price", "prices",
        "money", "needs", "looking", "suggest", "please", "recommend", "something", "vehicle", "vehicles", "range", "think",
        "great", "ideal", "other", "right", "first", "later", "since", "still", "being", "while", "every", "never", "again"}

# (key, pattern).  Order matters: the more specific phrase must come before the general one.
EXTREMES = [
    ("service_asc", r"lowest maintenance|cheapest to maintain|lowest service|least maintenance|lowest running cost|cheapest maintenance|cheapest service|cheapest to run"),
    ("mileage_desc", r"best mileage|highest mileage|most fuel efficient|most efficient|best fuel economy|best average|maximum mileage|max mileage|highest average|best range|longest range"),
    ("power_desc", r"fastest|quickest|most powerful|highest power|best performance|top speed|most horsepower|maximum power|max power"),
    ("seats_desc", r"biggest|largest|most spacious|most seats|maximum seats|most seating|max seats"),
    ("price_desc", r"most expensive|costliest|priciest|most costly|highest pric\w*|top of the line|flagship|most luxurious"),
    ("price_asc", r"cheapest|least expensive|lowest pric\w*|most affordable|least costly|lowest cost"),
]
EXTREME_LABEL = {"price_desc": "Most expensive", "price_asc": "Lowest price", "mileage_desc": "Best mileage",
                 "power_desc": "Most powerful", "seats_desc": "Most seats", "service_asc": "Lowest running cost"}
SPACE = r"spacious|roomy|big car|large car|lots of space|more space|\btall\b|legroom|leg room|headroom|head room|\d\s*'\s*\d|\d\s*(?:feet|ft|foot)\b|\bdog\b|\bpets?\b|luggage|boot space"
COLOUR = r"\b(pink|red|blue|white|black|grey|gray|silver|yellow|orange|purple|brown|golden|gold|maroon|beige)\b|\bcolou?rs?\b|\bpaint\b"
LADIES = r"\bladies\b|\blady\b|\bwomen\b|\bwomen's\b|\bwoman\b|\bgirls?\b|\bfemale\b"
STYLISH = r"stylish|sleek|good[\s-]?looking|looks good|nice looking|head[\s-]?turn\w*|attractive|handsome|sporty look|cool looking"
BIG_TYRES = r"big tyres?|big wheels?|large wheels?|wide tyres?|fat tyres?|bigger wheels?|bigger tyres?|alloy"
SOUND = r"sound system|music system|audio|speakers?|stereo|woofer|bose|harman|\bjbl\b|bang olufsen|burmester|good music"
RATING = r"\b(good|well|highly|top|best)[\s-]+rated\b|\bratings?\b|\breviews?\b"
NOTE_TEXT = {
    "colour": "Paint colours aren't in our data, so colour was not used - most models come in several shades, so check availability with the dealer.",
    "rating": "Owner ratings and reviews aren't in our data, so they were not used.",
    "tyres": "Wheel and tyre sizes aren't in our data; SUVs and off-roaders usually have the biggest tyres, so those are favoured.",
    "sound": "Audio systems vary by trim and aren't in our data; premium and luxury models more often offer branded systems (Bose, Harman Kardon ...), so those are favoured.",
    "entry": "Seat height and door size aren't in our data; SUVs and MPVs sit higher than sedans and hatchbacks, so those are favoured.",
    "style": "Style is subjective and not in our data; SUVs and coupes are favoured as the more eye-catching shapes.",
}
# ---- follow-up phrases ("cheaper", "only automatic", "bigger") that change an earlier search instead of starting a new one
RESET = r"\b(start over|start again|reset|new search|clear (all|everything)|forget (that|everything|it))\b"
CHEAPER = r"\b(cheaper|less expensive|lower (the )?(price|budget)|reduce (the )?budget|more affordable|budget[\s-]?friendly|lesser price)\b"
PRICIER = r"\b(more expensive|pricier|costlier|more premium|upgrade|step up|something better|higher end|better car)\b"
RAISE = r"\b(increase|raise|stretch|higher|bigger|more)\s+(the\s+)?budget\b|can spend more|afford more"
BIGGER = r"\b(bigger|larger|roomier|more space|more spacious|more seats|extra seats|more room)\b"
SMALLER = r"\b(smaller|more compact|tinier)\b"
MORE_MILEAGE = r"\b(more|better|higher|great|good)\s+(mileage|efficiency|fuel economy)\b|\bmore fuel efficient\b"
DROP = r"\b(remove|drop|ignore|forget|skip)\s+(?:the\s+)?(budget|brand|fuel|body|seats?|gearbox|transmission|mileage)\b"
DROP_KEYS = {"budget": ["budget", "min_budget"], "brand": ["brands", "exclude_brands"], "fuel": ["fuels", "exclude_fuels"],
             "body": ["body", "exclude_bodies", "soft_body", "body_in"], "seat": ["seats", "seats_exact", "seats_target"], "seats": ["seats", "seats_exact", "seats_target"],
             "gearbox": ["transmission"], "transmission": ["transmission"], "mileage": ["min_mileage"]}
ULTRA = r"billionaire|millionaire|ultra[\s-]?(?:luxury|rich|premium|lux)|super[\s-]?(?:luxury|luxurious|rich)|richest|money\s+(?:is\s+)?no\s+(?:issue|object|problem)|(?:price|cost)\s+(?:doesn'?t|does not|dont|don't)\s+matter|cost\s+no\s+object|unlimited\s+budget|sky\s+is\s+the\s+limit"
ELDERLY = r"\bold\b.{0,15}\b(?:parents?|people|folks|mother|father|mom|dad|grandparents|grandma|grandpa)\b|\b(?:parents?|mother|father|mom|dad|grandparents|grandma|grandpa)\b.{0,12}\bare\s+old\b|elderly|\bseniors?\b|old age|\baged\b|\bknee|back pain|bad back|arthritis|wheelchair|easy (?:to )?(?:enter|entry|get in|get out|sit|board|ingress|egress)|high seat|sits? high|tall seat"
NERVOUS = r"scared|afraid|nervous|\bfear\b|frighten|terrified|panic|anxious|not confident|no confidence|lack confidence|new to driving|bad at driving|poor driver|weak driver|bad driver"
OFFROAD = r"off[\s-]?road\w*|4x4|4wd|\bmud\b|\btrails?\b|\btrek\w*|rugged|jungle|desert|rough terrain|dirt track|rock crawl\w*"
SOFT_ROUGH = r"adventure|rough|hilly|\bhills?\b|ghat|mountain|himalaya\w*|ladakh|spiti|village|bad roads|rural|potholes|uneven|waterlogg\w*|flood"
NEG = r"(?:not interested in|other than|anything but|apart from|dont want|don't want|do not want|dont like|don't like|without|except|excluding|avoid|never|hate|not|no)"
ITEM = r"(?:a\s+|an\s+|any\s+|the\s+)?"
SQUASH = re.compile(r"[^a-z0-9]")


def squash(s):
    return SQUASH.sub("", s.lower())


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def new_prefs():
    return dict(budget=None, min_budget=None, fuels=[], exclude_fuels=[], transmission=None, seats=None, seats_exact=False,
                seats_target=None, body=None, exclude_bodies=[], brands=[], exclude_brands=[], similar=None, min_year=None,
                min_mileage=None, segment=[], soft_segment=[], soft_transmission=None, notes=[], extreme_more=[], body_in=[], prefer_body=[], ultra=False, offroad=False, easy_drive=False, extreme=None, soft_body=[], soft_fuel=[], use=None,
                performance_priority=False, mileage_priority=False, maintenance_priority=False, budget_priority=False,
                premium=False)


class Understander:
    def __init__(self, models, model_brand, lex):
        self.models = list(models)
        self.model_brand = model_brand
        self.brands = lex["brands"]
        self.ambiguous = set(lex["ambiguous"])
        self.origins = lex["origins"]
        self.model_key = {squash(m): m for m in self.models}
        for phrase, model in lex["aliases"].items():
            self.model_key[squash(phrase)] = model
        # phrases that must be glued into one token before parsing ("range rover sport" -> "rangeroversport")
        phrases = {m.lower() for m in self.models if re.search(r"[\s-]", m) and not (len(m) <= 4 and " " in m)}  # "BE 6" is too ambiguous
        phrases |= {k.lower() for k in lex["aliases"] if re.search(r"[\s-]", k)}
        self.multi = [(re.compile(r"\b" + r"[\s-]*".join(re.escape(w) for w in re.split(r"[\s-]+", ph)) + r"\b"), squash(ph))
                      for ph in sorted(phrases, key=lambda s: (-len(s), s))]
        self.vocab = sorted(set(KEYWORDS) | set(self.brands) | set(self.origins) | set(self.model_key))
        self.known = set(self.vocab) | STOP
        self.keywords = sorted(set(BODY_WORDS) | set(FUEL_WORDS))   # the only targets a 4-letter typo may be fixed to
        self.vocab_no_models = sorted(set(KEYWORDS) | set(self.brands) | set(self.origins))
        self.all_brands = sorted(set(self.brands.values()))

    # ---- typo correction: only words that are not already known, same first letter, small edit distance
    def correct(self, t):
        def fix(m):
            w = m.group(0)
            if len(w) < 4 or w in self.known:
                return w
            # 4-letter words ("sedn") only match body/fuel words; 5-letter ones keywords/brands; model names need 6+ letters ("carry" is not "Camry")
            pool, limit = (self.keywords, 1) if len(w) == 4 else (self.vocab_no_models, 1) if len(w) == 5 else (self.vocab, 1 if len(w) <= 7 else 2)
            best, bd = None, 99
            for v in pool:
                if v[0] != w[0] or abs(len(v) - len(w)) > 2:
                    continue
                d = lev(w, v)
                if d < bd:
                    best, bd = v, d
            return best if best and bd <= limit else w
        return re.sub(r"[a-z]+", fix, t)

    def normalise(self, text):
        t = text.lower().replace("₹", " ").replace("rs.", " ").replace("’", "'")
        t = re.sub(r"\bland[\s-]*rover\b", "landrover", t)
        t = re.sub(r"\brolls[\s-]*royce\b", "rollsroyce", t)
        t = re.sub(r"\bmercedes[\s-]*benz\b", "mercedesbenz", t)
        t = re.sub(r"\baston[\s-]*martin\b", "astonmartin", t)
        t = re.sub(r"\bmaruti[\s-]*suzuki\b", "maruti", t)
        t = re.sub(r"\bsports?[\s-]*cars?\b|\bsupercars?\b", "supercar", t)
        t = re.sub(r"\b(i|ev|xuv)\s+(\d+)\b", r"\1\2", t)
        for rx, key in self.multi:
            t = rx.sub(key, t)
        return self.correct(t)

    @staticmethod
    def budget(t):
        """-> (min_price, max_price) in rupees; either may be None."""
        m = re.search(NUM + r"\s*(?:(?:crore|crores|cr|lakh|lakhs|lac|lacs|l)\b)?\s*(?:-|to|and)\s*" + NUM + r"\s*" + UNIT, t)
        if m:
            mult = 1e7 if m[3].startswith("c") else 1e5
            lo, hi = sorted((float(m[1]) * mult, float(m[2]) * mult))
            return lo, hi
        m = re.search(NUM + r"\s*" + UNIT, t)
        if m:
            val = float(m[1]) * (1e7 if m[2].startswith("c") else 1e5)
            ctx, after = t[max(0, m.start() - 20):m.start()], t[m.end():m.end() + 12]
        else:
            m = re.search(r"(?<![\d,.])(\d{1,3}(?:,\d{2,3})+|\d{6,9})(?![\d,])", t)
            if m:
                val = float(m[1].replace(",", ""))
                ctx, after = t[max(0, m.start() - 20):m.start()], t[m.end():m.end() + 12]
            else:
                m = re.search(r"(?:under|below|within|upto|up to|max(?:imum)?|budget(?: of)?|less than)\s*" + NUM + r"\b(?!\s*(?:km|kmpl|seat|cc|k\b))", t)
                if m and float(m[1]) <= 100:
                    return None, float(m[1]) * 1e5
                m = re.fullmatch(r"\s*" + NUM + r"\s*", t)
                if m and float(m[1]) <= 100:
                    return None, float(m[1]) * 1e5
                return None, None
        if re.search(r"(no|not)\s+(more than|above|over|beyond|exceeding)\s*$", ctx):
            return None, val
        if re.search(r"(around|about|approx\w*|roughly|near|nearly|close to)\s*$", ctx):
            return val * 0.85, val * 1.15
        if re.search(r"(above|over|more than|atleast|at least|minimum|min|starting|from|beyond)\s*$", ctx) or re.match(r"\s*(\+|plus|and above|or more)", after):
            return val, None
        return None, val

    def refine(self, prev, text, ref_price=None):
        """Apply a follow-up ("cheaper", "only diesel", "bigger") to the preferences of the previous search."""
        t = " " + text.lower() + " "
        if re.search(RESET, t):
            return self.extract(re.sub(RESET, " ", text.lower()))
        new = self.extract(text)
        base = new_prefs()
        cur = copy.deepcopy(base)
        cur.update(copy.deepcopy(prev))
        cur["notes"] = []
        for k, v in new.items():
            if k in ("exclude_fuels", "exclude_bodies", "exclude_brands"):
                cur[k] = cur[k] + [x for x in v if x not in cur[k]]
            elif k == "notes":
                cur[k] = v
            elif v != base[k]:
                cur[k] = copy.deepcopy(v)
        if new["budget"] or new["min_budget"]:
            cur["budget"], cur["min_budget"] = new["budget"], new["min_budget"]
        if new["extreme"]:
            cur["extreme_more"] = new["extreme_more"]
        if new["seats"]:
            cur["seats_target"] = None
        # changing your mind: "diesel" after "no diesel" (and the other way round)
        for pos, neg in (("fuels", "exclude_fuels"), ("brands", "exclude_brands")):
            cur[neg] = [x for x in cur[neg] if x not in new[pos]]
            cur[pos] = [x for x in cur[pos] if x not in new[neg]]
        if new["body"]:
            cur["exclude_bodies"] = [x for x in cur["exclude_bodies"] if x != new["body"]]
        cur["exclude_bodies"] = [x for x in cur["exclude_bodies"] if x != cur["body"]]
        if cur["body"]:
            cur["soft_body"] = []

        ref = prev.get("budget") or ref_price
        spoken_budget = bool(new["budget"] or new["min_budget"])
        for m in re.finditer(DROP, t):
            for key in DROP_KEYS[m.group(2)]:
                cur[key] = base[key]
        if re.search(CHEAPER, t) and not spoken_budget:
            if ref:
                step = 0.5 if prev.get("extreme") == "price_desc" else 0.8     # from the very top of the market, 20% is no step at all
                cur["budget"], cur["min_budget"] = _round_to(ref * step, 1e4), None
            cur["budget_priority"], cur["premium"] = True, False
            if cur["extreme"] == "price_desc":
                cur["extreme"] = None
            if cur["soft_segment"] == ["Premium", "Luxury"]:
                cur["soft_segment"] = []
        elif re.search(PRICIER, t) and not spoken_budget:
            if ref_price or ref:     # a step up: from 10% above what was shown to about double
                top = ref_price or ref
                cur["min_budget"], cur["budget"] = _round_to(top * 1.1, 1e4), _round_to(top * 2.2, 1e4)
            cur["premium"], cur["budget_priority"] = True, False
            if cur["extreme"] == "price_asc":
                cur["extreme"] = None
        elif re.search(RAISE, t) and not spoken_budget:
            if prev.get("budget"):
                cur["budget"] = _round_to(prev["budget"] * 1.3, 1e4)
            elif ref_price:
                cur["budget"] = _round_to(ref_price * 1.5, 1e4)
        if re.search(BIGGER, t) and not new["seats"]:
            if (cur["seats"] or 0) < 7:
                cur["seats"], cur["seats_exact"], cur["seats_target"] = 7, False, None
            else:                    # already 7+: keep the filter, lean towards the most seats
                cur["seats_target"] = 8
        if re.search(SMALLER, t):
            cur["seats"], cur["seats_exact"], cur["seats_target"] = None, False, None
            if not cur["body"]:
                cur["soft_body"] = ["Hatchback", "Sedan"]
        if re.search(MORE_MILEAGE, t):
            cur["mileage_priority"] = True
            if cur["min_mileage"]:
                cur["min_mileage"] = math.floor(cur["min_mileage"] * 1.15 * 10 + 0.5) / 10
        return cur

    def extract(self, text):
        t = " " + self.normalise(text) + " "
        p = new_prefs()

        # "zero petrol expenses", "petrol free" -> the person wants an electric car
        nofuel = r"(zero|no|without)\s+(petrol|fuel|diesel)\s+(expenses?|costs?|bills?|spend\w*)|(petrol|fuel)[\s-]*free|zero\s+(petrol|fuel)"
        if re.search(nofuel, t):
            p["fuels"].append("Electric")
            t = re.sub(nofuel, " ", t)

        # "billionaire level", "money is no issue": the very top of the market
        if re.search(ULTRA, t):
            p["ultra"] = p["premium"] = True
            t = re.sub(ULTRA, " ", t)

        # "no budget limit", "not too expensive"
        nobud = r"(no|unlimited|any)\s+budget(\s+limit)?|money\s+(is\s+)?no\s+(issue|object|problem)"
        if re.search(nobud, t):
            p["premium"] = True
            t = re.sub(nobud, " ", t)
        notexp = r"not\s+(too\s+|very\s+|so\s+)?(expensive|costly|pricey)"
        if re.search(notexp, t):
            p["budget_priority"] = True
            t = re.sub(notexp, " ", t)

        # "most expensive", "cheapest", "fastest" ... -> rank by that quality; several together are ranked by all of them (earliest = main one)
        original, found = t, []
        for name, pat in EXTREMES:
            m = re.search(pat, t)
            if m:
                found.append((original.find(m.group(0)), name))
                t = re.sub(pat, " ", t)
                if name == "price_desc":
                    p["premium"] = True
                elif name == "price_asc":
                    p["budget_priority"] = True
                elif name == "mileage_desc":
                    p["mileage_priority"] = True
                elif name == "power_desc":
                    p["performance_priority"] = True
                elif name == "seats_desc":
                    p["seats_target"] = 8
                else:
                    p["maintenance_priority"] = True
        if found:
            names = [name for _, name in sorted(found)]
            p["extreme"], p["extreme_more"] = names[0], names[1:]

        # negations: "no diesel", "not automatic", "without suv", "avoid tata", "I don't want Tata or Mahindra"
        def kind(w):
            if w in FUEL_WORDS:
                return "fuel"
            if w in ("automatic", "auto", "amt", "cvt", "manual"):
                return "gear"
            if w in BODY_WORDS:
                return "body"
            if w in self.brands or w in self.origins:
                return "brand"
            return None

        def exclude(w):
            k = kind(w)
            if k == "fuel":
                p["exclude_fuels"].append(FUEL_WORDS[w])
            elif k == "gear":
                p["transmission"] = "Automatic" if w == "manual" else "Manual"
            elif k == "body":
                p["exclude_bodies"].append(BODY_WORDS[w])
            else:
                p["exclude_brands"].extend(b for b in ([self.brands[w]] if w in self.brands else self.origins[w]) if b not in p["exclude_brands"])

        def negate(m):
            first = m.group(1)
            if not kind(first):
                return m.group(0)
            exclude(first)
            rest = m.group(2) or ""
            for tm in re.finditer(r"\s*(,|or|and|nor|&)\s*" + ITEM + r"([a-z0-9]+)", rest):
                sep, w = tm.group(1), tm.group(2)
                # "or"/"nor" keep negating anything ("no manual or diesel"); "and"/"," only continue within the same kind ("no tata and mahindra"),
                # because "no diesel, automatic" means: no diesel, and I do want automatic.
                if kind(w) and (sep in ("or", "nor") or kind(w) == kind(first)):
                    exclude(w)
                else:
                    return " " + rest[tm.start():]
            return " "
        t = re.sub(r"\b" + NEG + r"\s+" + ITEM + r"([a-z0-9]+)((?:\s*(?:,|or|and|nor|&)\s*" + ITEM + r"[a-z0-9]+)*)", negate, t)

        for w, key in (("mileage", "mileage_priority"), ("price", "budget_priority"), ("maintenance", "maintenance_priority"), ("performance", "performance_priority")):
            if re.search(r"don'?t care (?:about )?" + w, t):
                p[key] = None
                t = re.sub(r"don'?t care (?:about )?" + w, " ", t)

        p["min_budget"], p["budget"] = self.budget(t)
        toks = re.findall(r"[a-z0-9]+", t)

        for i, w in enumerate(toks):
            for b in self.origins.get(w, []):
                if b not in p["brands"] and b not in p["exclude_brands"]:
                    p["brands"].append(b)
            if w in self.brands and self.brands[w] not in p["brands"] and self.brands[w] not in p["exclude_brands"]:
                p["brands"].append(self.brands[w])
            if w in self.model_key and p["similar"] is None:
                if w in self.ambiguous and not (i and toks[i - 1] in self.brands):
                    continue
                p["similar"] = self.model_key[w]
            if w in FUEL_WORDS and FUEL_WORDS[w] not in p["fuels"] and FUEL_WORDS[w] not in p["exclude_fuels"]:
                p["fuels"].append(FUEL_WORDS[w])
        if re.search(r"\bgas\b", t) and "Petrol" not in p["fuels"] and "Petrol" not in p["exclude_fuels"]:
            p["fuels"].append("Petrol")
        if re.search(r"battery|zero emission", t) and "Electric" not in p["fuels"]:
            p["fuels"].append("Electric")
        if re.search(r"\beco|green|environment|pollution", t) and not p["fuels"]:
            p["soft_fuel"] = ["Electric", "CNG", "Hybrid"]
        # "Hyundai Creta" names the brand and the model: the model already implies the brand
        if p["similar"] and len(p["brands"]) == 1 and p["brands"][0] == self.model_brand.get(p["similar"]):
            p["brands"] = []

        if p["transmission"] is None:
            auto = re.search(r"\b(automatic|auto|amt|cvt|dct|dsg)\b|no gear|no clutch|clutchless|easy to drive|effortless|without clutch", t)
            manual = re.search(r"\b(manual|stick)\b|gear shift", t)
            if auto and not manual:
                p["transmission"] = "Automatic"
            elif manual and not auto:
                p["transmission"] = "Manual"

        m = re.search(r"(\d+|" + "|".join(WORDS) + r")\s*\+?[\s-]*(?:seater|seats?|seating|people|persons|passengers|members)", t) \
            or re.search(r"family of (\d+|" + "|".join(WORDS) + r")", t)
        if m:
            p["seats"] = int(m[1]) if m[1].isdigit() else WORDS[m[1]]
            p["seats_exact"] = p["seats"] <= 2          # a "2 seater" means exactly two seats
        elif re.search(r"\b(big|large|joint|extended)\s+family|grandparents?|grandma|grandpa|in[\s-]?laws", t):
            p["seats"] = 7
        elif re.search(r"family|kids|children|parents|\bwife\b|husband|\bkid\b", t):
            p["seats"] = 5
        if p["seats"] is None and p["seats_target"] is None and re.search(SPACE, t):
            p["seats_target"] = 7

        for w in toks:
            if w in BODY_WORDS and BODY_WORDS[w] not in p["exclude_bodies"]:
                p["body"] = BODY_WORDS[w]

        m = re.search(NUM + r"\s*\+?\s*(?:km\s*/\s*l|kmpl|kpl|km per l\w*|kilometre per litre)", t) \
            or re.search(r"(?:mileage|average)\D{0,15}?" + NUM + r"(?!\d)(?!\s*(?:lakh|lac|l\b|cr|seat|k\b))", t)
        if m:
            p["min_mileage"], p["mileage_priority"] = float(m[1]), True
        elif re.search(r"mileage|fuel efficient|fuel economy|economy|efficient|\baverage\b|save fuel|less fuel|fuel consumption|kmpl", t):
            p["mileage_priority"] = True
        if re.search(r"\bfast|speed|powerful|\bpower\b|performance|sporty|quick|pickup|acceleration|torque", t):
            p["performance_priority"] = True
        if re.search(r"maintenance|maintain|service cost|servicing|running cost|upkeep|cheap service|low service", t):
            p["maintenance_priority"] = True
        if re.search(r"cheap|affordable|low budget|economical|value for money|sast[aei]|kam budget|pocket friendly|tight budget", t):
            p["budget_priority"] = True
        if re.search(r"premium|luxur|expensive|high end|top end|executive|classy|impress|client|\\bceo\\b|\\bboss\\b|\\brich\\b|wealthy|prestige|show ?off|chauffeur", t):
            p["premium"] = True
        if re.search(r"luxur", t):
            p["segment"] = ["Luxury"]
        elif re.search(r"premium|expensive|high end|top end|executive|classy|impress|client|\\bceo\\b|\\bboss\\b|\\brich\\b|wealthy|prestige|show ?off|chauffeur", t):
            p["soft_segment"] = ["Premium", "Luxury"]

        m = re.search(r"(20[12]\d)\s*(?:model|or newer|and above|onwards|\+)", t) or re.search(r"(?:since|from|newer than)\s*(20[12]\d)", t)
        if m:
            p["min_year"] = int(m[1])
        elif re.search(r"after\s*(20[12]\d)", t):
            p["min_year"] = int(re.search(r"after\s*(20[12]\d)", t)[1]) + 1
        elif re.search(r"latest|newest|new model|recent|brand new|newer|modern", t):
            p["min_year"] = 2023

        soft = []
        if p["similar"] == "City":
            t = re.sub(r"\bcity\b", " ", t)      # "Honda City" is a car, not a driving style
        if re.search(r"\bcity\b|traffic|parking|narrow|compact|\bsmall\b|tiny", t):
            soft, p["use"] = ["Hatchback", "Sedan"], "city driving"
            if "traffic" in t and p["transmission"] is None:
                p["transmission"] = "Automatic"
        if re.search(r"daily|commute|office|\bwork\b", t):
            soft, p["use"], p["mileage_priority"] = ["Hatchback", "Sedan"], "daily commute", True
        if re.search(r"first car|beginner|learner|new driver|student|college", t):
            soft, p["use"], p["budget_priority"] = ["Hatchback"], "first car", True
        if re.search(r"long drive|road trip|highway|touring|travel|outstation", t):
            soft, p["use"], p["performance_priority"] = ["Sedan", "SUV", "MPV"], "long drives", True
        if re.search(OFFROAD, t):          # a real off-roader: Thar, Jimny, Bolero, Defender ... not a crossover
            soft, p["use"], p["offroad"] = ["SUV"], "off-road driving", True
        elif re.search(SOFT_ROUGH, t):
            soft, p["use"], p["performance_priority"] = ["SUV"], "rough roads", True
        if re.search(r"taxi|commercial|\bcab\b|fleet|\buber\b|\bola\b", t):
            soft, p["use"], p["mileage_priority"], p["maintenance_priority"] = ["Sedan", "MPV"], "commercial use", True, True
            if not p["body"]:                   # Ola/Uber/fleet cars are sedans and MPVs, not crossovers
                p["body_in"] = ["Sedan", "MPV"]
            if not p["fuels"]:
                p["soft_fuel"] = ["CNG", "Diesel"]
        if re.search(SPACE, t):
            soft, p["use"] = ["SUV", "MPV"], "extra space"
        if re.search(ELDERLY, t):          # elderly passengers: easy to get in and out, relaxed to drive
            soft, p["use"], p["prefer_body"] = ["SUV", "MPV"], "easy entry for elders", ["MPV"]   # tall MPVs (Ertiga, Carens, Innova) are the classic choice
            if p["transmission"] is None:
                p["soft_transmission"] = "Automatic"
            p["notes"].append(["Seat height", NOTE_TEXT["entry"]])
        if re.search(NERVOUS, t):          # nervous driver: light, compact, automatic, no big engines
            soft, p["use"], p["easy_drive"], p["prefer_body"] = ["Hatchback", "SUV"], "confident, easy driving", True, ["Hatchback"]
            if p["transmission"] is None:
                p["soft_transmission"] = "Automatic"
        if re.search(LADIES, t):          # asked for an easy-to-drive car: compact, automatic
            soft, p["use"] = ["Hatchback"], "easy city driving"
            if p["transmission"] is None:
                p["soft_transmission"] = "Automatic"
        if re.search(STYLISH, t):
            soft, p["use"] = ["SUV", "Coupe"], "stylish looks"
            p["notes"].append(["Style", NOTE_TEXT["style"]])
        if re.search(BIG_TYRES, t):
            soft, p["use"] = ["SUV"], "bigger wheels"
            p["notes"].append(["Tyre size", NOTE_TEXT["tyres"]])
        if re.search(SOUND, t):
            p["use"] = p["use"] or "premium audio"
            if not p["segment"] and not p["soft_segment"]:
                p["soft_segment"] = ["Premium", "Luxury"]
            p["notes"].append(["Sound system", NOTE_TEXT["sound"]])
        cm = re.search(COLOUR, t)
        if cm:
            word = cm.group(1)
            p["notes"].append([f"Colour ({word})" if word else "Colour", NOTE_TEXT["colour"]])
        if re.search(RATING, t):
            p["notes"].append(["Ratings", NOTE_TEXT["rating"]])
        if re.search(r"supercar", t):
            p["use"], p["performance_priority"] = "sports driving", True
            if not p["body"]:
                p["body"] = "Coupe"
        if not p["body"]:
            p["soft_body"] = soft
        for k in ("performance_priority", "mileage_priority", "maintenance_priority", "budget_priority"):
            p[k] = bool(p[k])
        return p


def inr(n):
    """12345678 -> '1,23,45,678' (Indian digit grouping)."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    return re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", s[:-3]) + "," + s[-3:]


def _half_up(x):
    """Round to 2 decimals, halves upward (same as the browser engine; Python's own formatting rounds halves to even)."""
    return math.floor(x * 100 + 0.5) / 100


def _round_to(x, step):
    return math.floor(x / step + 0.5) * step


def sanitize_prefs(d, brands, models):
    """Preferences sent back by the browser are untrusted input: keep only well-formed, known values."""
    out = new_prefs()
    if not isinstance(d, dict):
        return out
    FUELS, BODIES = {"Petrol", "Diesel", "Electric", "CNG", "Hybrid"}, {"SUV", "Sedan", "Hatchback", "MPV", "Coupe"}
    SEGMENTS, EXTREME_KEYS = {"Budget", "Mainstream", "Premium", "Luxury"}, set(EXTREME_LABEL)
    lst = lambda v, ok: [x for x in v if isinstance(x, str) and x in ok] if isinstance(v, list) else []
    num = lambda v, lo, hi: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi else None
    out["budget"], out["min_budget"] = num(d.get("budget"), 1, 1e10), num(d.get("min_budget"), 1, 1e10)
    out["min_mileage"], out["seats_target"] = num(d.get("min_mileage"), 1, 100), num(d.get("seats_target"), 1, 9)
    out["seats"] = int(num(d.get("seats"), 1, 9)) if num(d.get("seats"), 1, 9) else None
    out["min_year"] = int(num(d.get("min_year"), 2000, 2035)) if num(d.get("min_year"), 2000, 2035) else None
    out["seats_exact"] = d.get("seats_exact") is True
    for k, ok in (("fuels", FUELS), ("exclude_fuels", FUELS), ("exclude_bodies", BODIES), ("soft_body", BODIES), ("brands", set(brands)),
                  ("exclude_brands", set(brands)), ("segment", SEGMENTS), ("soft_segment", SEGMENTS), ("soft_fuel", FUELS)):
        out[k] = lst(d.get(k), ok)
    out["transmission"] = d.get("transmission") if d.get("transmission") in ("Automatic", "Manual") else None
    out["soft_transmission"] = d.get("soft_transmission") if d.get("soft_transmission") in ("Automatic", "Manual") else None
    out["body"] = d.get("body") if d.get("body") in BODIES else None
    out["similar"] = d.get("similar") if d.get("similar") in set(models) else None
    out["extreme"] = d.get("extreme") if d.get("extreme") in EXTREME_KEYS else None
    out["use"] = d["use"][:40] if isinstance(d.get("use"), str) else None
    out["extreme_more"] = [x for x in d.get("extreme_more", []) if x in EXTREME_KEYS] if isinstance(d.get("extreme_more"), list) else []
    out["body_in"] = lst(d.get("body_in"), BODIES)
    out["prefer_body"] = lst(d.get("prefer_body"), BODIES)
    for k in ("ultra", "offroad", "easy_drive"):
        out[k] = d.get(k) is True
    for k in ("performance_priority", "mileage_priority", "maintenance_priority", "budget_priority", "premium"):
        out[k] = d.get(k) is True
    return out


def money(v):
    """Rupees -> '₹7.5 lakh' / '₹1.25 crore'."""
    if v >= 1e7:
        return "₹" + f"{_half_up(v / 1e7):.2f}".rstrip("0").rstrip(".") + " crore"
    return "₹" + f"{_half_up(v / 1e5):.2f}".rstrip("0").rstrip(".") + " lakh"


def summarise(p):
    s = []
    if p["min_budget"] and p["budget"]:
        s.append(("Budget", f"{money(p['min_budget'])} – {money(p['budget'])}"))
    elif p["budget"]:
        s.append(("Budget", f"Up to {money(p['budget'])}"))
    elif p["min_budget"]:
        s.append(("Budget", f"From {money(p['min_budget'])}"))
    if p["brands"]:
        s.append(("Brand", " / ".join(p["brands"])))
    if p["similar"]:
        s.append(("Like", p["similar"]))
    if p["fuels"]:
        s.append(("Fuel", " / ".join(p["fuels"])))
    if p["transmission"]:
        s.append(("Gearbox", p["transmission"]))
    if p["seats"]:
        s.append(("Seats", f"{p['seats']}" if p["seats_exact"] else f"{p['seats']}+"))
    if p["body"]:
        s.append(("Body", p["body"]))
    if p["min_mileage"]:
        s.append(("Mileage", f"{p['min_mileage']:g}+ km/l"))
    if p["min_year"]:
        s.append(("Year", f"{p['min_year']}+"))
    if p["body_in"]:
        s.append(("Body", " / ".join(p["body_in"])))
    if p["ultra"]:
        s.append(("Tier", "Ultra-luxury"))
    elif p["segment"]:
        s.append(("Tier", " / ".join(p["segment"])))
    if p["offroad"]:
        s.append(("Type", "Off-road capable"))
    if p["extreme"]:
        s.append(("Rank by", " + ".join(EXTREME_LABEL[k] for k in [p["extreme"]] + p["extreme_more"])))
    avoid = p["exclude_fuels"] + p["exclude_bodies"] + p["exclude_brands"]
    if avoid:
        s.append(("Avoid", ", ".join(avoid)))
    if p["use"]:
        s.append(("Best for", p["use"]))
    if p["notes"]:
        s.append(("Not in data", ", ".join(x[0] for x in p["notes"])))
    prio = [n for n, k in [("performance", "performance_priority"), ("mileage", "mileage_priority"),
                           ("low maintenance", "maintenance_priority"), ("low price", "budget_priority"), ("premium", "premium")] if p[k]]
    if prio and not p["extreme"]:
        s.append(("Priority", ", ".join(prio)))
    return [{"label": a, "value": b} for a, b in s]
