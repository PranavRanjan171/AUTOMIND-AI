/* In-browser copy of the recommender (mirrors nlu.py + recommender.py line by line).
   Used automatically when the server is unreachable, so the site keeps working on static hosting.
   tests/test_parity.py checks that both engines return the same cars. */
(function () {
    const D = window.CARS_DATA;
    if (!D) return;
    const has = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
    const PREFER_PENALTY = 0.12, LATEST_YEAR = 2025, SOFT_PENALTY = 0.35, RECENCY_PENALTY = 0.03, SCORE_SHARPNESS = 1.2, MAX_PER_BRAND = 2;

    /* ---------------- data ---------------- */
    const cars = D.rows.map(r => ({
        Brand: D.brands[r[0]], Model: D.models[r[1]], Year: r[2], Price: r[3], Mileage: r[4], Range_km: r[5], Engine_CC: r[6],
        Power_bhp: r[7], Seating_Capacity: r[8], Service_Cost: r[9], Cost_Per_Km: r[10], Fuel_Type: D.fuels[r[11]], Transmission: D.trans[r[12]],
        Body_Type: D.body[D.models[r[1]]], Segment: D.segment[D.models[r[1]]],
    }));
    const ULTRA_SET = new Set(D.ultra), OFFROAD_SET = new Set(D.offroad);
    cars.forEach(c => { c.Is_EV = c.Fuel_Type === "Electric"; c.Ultra_Luxury = ULTRA_SET.has(c.Model); c.Offroad = OFFROAD_SET.has(c.Model); });
    const FEATURES = ["Price", "Cost_Per_Km", "Power_bhp", "Service_Cost", "Seating_Capacity"];
    const LOG = new Set(["Price", "Cost_Per_Km", "Power_bhp", "Service_Cost"]);
    const T = (k, x) => LOG.has(k) ? Math.log10(x) : x;
    const popStd = v => { const m = v.reduce((a, b) => a + b, 0) / v.length; return Math.sqrt(v.reduce((a, b) => a + (b - m) ** 2, 0) / v.length) || 1; };
    const mean = v => v.reduce((a, b) => a + b, 0) / v.length;
    const MU = {}, SD = {};
    FEATURES.forEach(k => { const v = cars.map(c => T(k, c[k])); MU[k] = mean(v); SD[k] = popStd(v); });
    SD.Mileage = popStd(cars.filter(c => c.Mileage !== null).map(c => c.Mileage));
    SD.Range_km = popStd(cars.filter(c => c.Range_km !== null).map(c => c.Range_km));
    const quantile = (arr, q) => {
        const a = [...arr].sort((x, y) => x - y), pos = (a.length - 1) * q, lo = Math.floor(pos);
        return a[lo] + (a[Math.min(lo + 1, a.length - 1)] - a[lo]) * (pos - lo);
    };
    const median = arr => quantile(arr, 0.5);
    const inr = n => { const s = String(Math.trunc(n)); return s.length <= 3 ? s : s.slice(0, -3).replace(/(\d)(?=(\d\d)+$)/g, "$1,") + "," + s.slice(-3); };
    const halfUp = x => Math.floor(x * 100 + 0.5) / 100;
    const trim = s => s.replace(/0+$/, "").replace(/\.$/, "");
    const money = v => v >= 1e7 ? "₹" + trim(halfUp(v / 1e7).toFixed(2)) + " crore" : "₹" + trim(halfUp(v / 1e5).toFixed(2)) + " lakh";
    const num2 = x => String(+x);       // Python's {:g} for the values in this data set

    /* ---------------- language understanding ---------------- */
    const NUM = "(\\d+(?:\\.\\d+)?)", UNIT = "(crore|crores|cr|lakh|lakhs|lac|lacs|l)\\b";
    const WORDS = { two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8 };
    const BRANDS = D.lex.brands, ORIGINS = D.lex.origins, AMBIGUOUS = new Set(D.lex.ambiguous);
    const FUEL_WORDS = { petrol: "Petrol", gasoline: "Petrol", diesel: "Diesel", electric: "Electric", ev: "Electric", evs: "Electric", cng: "CNG", hybrid: "Hybrid", hybrids: "Hybrid" };
    const BODY_WORDS = { suv: "SUV", suvs: "SUV", sedan: "Sedan", sedans: "Sedan", hatchback: "Hatchback", hatchbacks: "Hatchback", hatch: "Hatchback",
        mpv: "MPV", muv: "MPV", minivan: "MPV", coupe: "Coupe", coupes: "Coupe" };
    const KEYWORDS = `petrol diesel electric cng gasoline hybrid automatic manual mileage maintenance service seater seats family cheap
affordable budget lakh lakhs crore under below above around about between premium luxury spacious compact small sedan
hatchback suv mpv muv minivan coupe supercar performance powerful sporty speed fast quick pickup average efficient economical
economy comfortable commute daily traffic highway adventure offroad taxi commercial latest newest without avoid people persons
passengers kmpl approximately roughly minimum maximum acceleration beginner learner student office parking kids children
parents expensive costliest priciest cheapest fastest quickest biggest largest luxurious
audio sound system speakers stereo music stylish sleek rated rating ratings reviews review colour color colours colors paint pink red blue white black grey gray silver yellow orange purple brown golden gold maroon beige ladies women woman female wheels tyres tyre alloy`.split(/\s+/);
    const STOP = new Set(["which", "where", "would", "could", "should", "their", "there", "about", "these", "those", "years", "price", "prices",
        "money", "needs", "looking", "suggest", "please", "recommend", "something", "vehicle", "vehicles", "range", "think",
        "great", "ideal", "other", "right", "first", "later", "since", "still", "being", "while", "every", "never", "again"]);
    const EXTREMES = [
        ["service_asc", "lowest maintenance|cheapest to maintain|lowest service|least maintenance|lowest running cost|cheapest maintenance|cheapest service|cheapest to run"],
        ["mileage_desc", "best mileage|highest mileage|most fuel efficient|most efficient|best fuel economy|best average|maximum mileage|max mileage|highest average|best range|longest range"],
        ["power_desc", "fastest|quickest|most powerful|highest power|best performance|top speed|most horsepower|maximum power|max power"],
        ["seats_desc", "biggest|largest|most spacious|most seats|maximum seats|most seating|max seats"],
        ["price_desc", "most expensive|costliest|priciest|most costly|highest pric\\w*|top of the line|flagship|most luxurious"],
        ["price_asc", "cheapest|least expensive|lowest pric\\w*|most affordable|least costly|lowest cost"],
    ];
    const EXTREME_LABEL = { price_desc: "Most expensive", price_asc: "Lowest price", mileage_desc: "Best mileage", power_desc: "Most powerful", seats_desc: "Most seats", service_asc: "Lowest running cost" };

    const SPACE = /spacious|roomy|big car|large car|lots of space|more space|\btall\b|legroom|leg room|headroom|head room|\d\s*'\s*\d|\d\s*(?:feet|ft|foot)\b|\bdog\b|\bpets?\b|luggage|boot space/;
    const COLOUR = /\b(pink|red|blue|white|black|grey|gray|silver|yellow|orange|purple|brown|golden|gold|maroon|beige)\b|\bcolou?rs?\b|\bpaint\b/;
    const LADIES = /\bladies\b|\blady\b|\bwomen\b|\bwomen's\b|\bwoman\b|\bgirls?\b|\bfemale\b/;
    const STYLISH = /stylish|sleek|good[\s-]?looking|looks good|nice looking|head[\s-]?turn\w*|attractive|handsome|sporty look|cool looking/;
    const BIG_TYRES = /big tyres?|big wheels?|large wheels?|wide tyres?|fat tyres?|bigger wheels?|bigger tyres?|alloy/;
    const SOUND = /sound system|music system|audio|speakers?|stereo|woofer|bose|harman|\bjbl\b|bang olufsen|burmester|good music/;
    const RATING = /\b(good|well|highly|top|best)[\s-]+rated\b|\bratings?\b|\breviews?\b/;
    const NOTE_TEXT = {
        colour: "Paint colours aren't in our data, so colour was not used - most models come in several shades, so check availability with the dealer.",
        rating: "Owner ratings and reviews aren't in our data, so they were not used.",
        tyres: "Wheel and tyre sizes aren't in our data; SUVs and off-roaders usually have the biggest tyres, so those are favoured.",
        sound: "Audio systems vary by trim and aren't in our data; premium and luxury models more often offer branded systems (Bose, Harman Kardon ...), so those are favoured.",
        style: "Style is subjective and not in our data; SUVs and coupes are favoured as the more eye-catching shapes.",
    };
    const ULTRA = /billionaire|millionaire|ultra[\s-]?(?:luxury|rich|premium|lux)|super[\s-]?(?:luxury|luxurious|rich)|richest|money\s+(?:is\s+)?no\s+(?:issue|object|problem)|(?:price|cost)\s+(?:doesn'?t|does not|dont|don't)\s+matter|cost\s+no\s+object|unlimited\s+budget|sky\s+is\s+the\s+limit/;
    const ELDERLY = /\bold\b.{0,15}\b(?:parents?|people|folks|mother|father|mom|dad|grandparents|grandma|grandpa)\b|\b(?:parents?|mother|father|mom|dad|grandparents|grandma|grandpa)\b.{0,12}\bare\s+old\b|elderly|\bseniors?\b|old age|\baged\b|\bknee|back pain|bad back|arthritis|wheelchair|easy (?:to )?(?:enter|entry|get in|get out|sit|board|ingress|egress)|high seat|sits? high|tall seat/;
    const NERVOUS = /scared|afraid|nervous|\bfear\b|frighten|terrified|panic|anxious|not confident|no confidence|lack confidence|new to driving|bad at driving|poor driver|weak driver|bad driver/;
    const OFFROAD = /off[\s-]?road\w*|4x4|4wd|\bmud\b|\btrails?\b|\btrek\w*|rugged|jungle|desert|rough terrain|dirt track|rock crawl\w*/;
    const SOFT_ROUGH = /adventure|rough|hilly|\bhills?\b|ghat|mountain|himalaya\w*|ladakh|spiti|village|bad roads|rural|potholes|uneven|waterlogg\w*|flood/;
    const NEG = "(?:not interested in|other than|anything but|apart from|dont want|don't want|do not want|dont like|don't like|without|except|excluding|avoid|never|hate|not|no)";
    const ITEM = "(?:a\\s+|an\\s+|any\\s+|the\\s+)?";
    NOTE_TEXT.entry = "Seat height and door size aren't in our data; SUVs and MPVs sit higher than sedans and hatchbacks, so those are favoured.";
    const squash = s => s.toLowerCase().replace(/[^a-z0-9]/g, "");
    const reEsc = w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const MODEL_KEY = {};
    D.models.forEach(m => { MODEL_KEY[squash(m)] = m; });
    Object.entries(D.lex.aliases).forEach(([k, v]) => { MODEL_KEY[squash(k)] = v; });
    const phrases = new Set(D.models.filter(m => /[\s-]/.test(m) && !(m.length <= 4 && m.includes(" "))).map(m => m.toLowerCase()));
    Object.keys(D.lex.aliases).filter(k => /[\s-]/.test(k)).forEach(k => phrases.add(k.toLowerCase()));
    const MULTI = [...phrases].sort((a, b) => b.length - a.length || (a < b ? -1 : a > b ? 1 : 0))
        .map(ph => [new RegExp("\\b" + ph.split(/[\s-]+/).map(reEsc).join("[\\s-]*") + "\\b", "g"), squash(ph)]);
    const KW = [...new Set([...Object.keys(BODY_WORDS), ...Object.keys(FUEL_WORDS)])].sort();
    const VOCAB_NO_MODELS = [...new Set([...KEYWORDS, ...Object.keys(BRANDS), ...Object.keys(ORIGINS)])].sort();
    const VOCAB = [...new Set([...KEYWORDS, ...Object.keys(BRANDS), ...Object.keys(ORIGINS), ...Object.keys(MODEL_KEY)])].sort();
    const KNOWN = new Set([...VOCAB, ...STOP]);
    const ALL_BRANDS = [...new Set(Object.values(BRANDS))].sort();

    function lev(a, b) {
        let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
        for (let i = 1; i <= a.length; i++) {
            const cur = [i];
            for (let j = 1; j <= b.length; j++) cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] !== b[j - 1] ? 1 : 0)));
            prev = cur;
        }
        return prev[b.length];
    }
    function correct(t) {
        return t.replace(/[a-z]+/g, w => {
            if (w.length < 4 || KNOWN.has(w)) return w;
            const pool = w.length === 4 ? KW : w.length === 5 ? VOCAB_NO_MODELS : VOCAB, limit = w.length <= 7 ? 1 : 2;
            let best = null, bd = 99;
            for (const v of pool) {
                if (v[0] !== w[0] || Math.abs(v.length - w.length) > 2) continue;
                const d = lev(w, v);
                if (d < bd) { best = v; bd = d; }
            }
            return best && bd <= limit ? best : w;
        });
    }
    function normalise(text) {
        let t = text.toLowerCase().replace(/₹/g, " ").replace(/rs\./g, " ").replace(/’/g, "'");
        t = t.replace(/\bland[\s-]*rover\b/g, "landrover").replace(/\brolls[\s-]*royce\b/g, "rollsroyce").replace(/\bmercedes[\s-]*benz\b/g, "mercedesbenz")
            .replace(/\baston[\s-]*martin\b/g, "astonmartin").replace(/\bmaruti[\s-]*suzuki\b/g, "maruti")
            .replace(/\bsports?[\s-]*cars?\b|\bsupercars?\b/g, "supercar").replace(/\b(i|ev|xuv)\s+(\d+)\b/g, "$1$2");
        for (const [rx, key] of MULTI) t = t.replace(rx, key);
        return correct(t);
    }
    function budget(t) {
        let m = t.match(new RegExp(NUM + "\\s*(?:(?:crore|crores|cr|lakh|lakhs|lac|lacs|l)\\b)?\\s*(?:-|to|and)\\s*" + NUM + "\\s*" + UNIT));
        if (m) {
            const mult = m[3].startsWith("c") ? 1e7 : 1e5, [lo, hi] = [+m[1] * mult, +m[2] * mult].sort((a, b) => a - b);
            return [lo, hi];
        }
        let val = null, ctx, after;
        m = t.match(new RegExp(NUM + "\\s*" + UNIT));
        if (m) {
            val = +m[1] * (m[2].startsWith("c") ? 1e7 : 1e5); ctx = t.slice(Math.max(0, m.index - 20), m.index); after = t.slice(m.index + m[0].length, m.index + m[0].length + 12);
        } else {
            m = t.match(/(?<![\d,.])(\d{1,3}(?:,\d{2,3})+|\d{6,9})(?![\d,])/);
            if (m) { val = +m[1].replace(/,/g, ""); ctx = t.slice(Math.max(0, m.index - 20), m.index); after = t.slice(m.index + m[0].length, m.index + m[0].length + 12); }
            else {
                m = t.match(new RegExp("(?:under|below|within|upto|up to|max(?:imum)?|budget(?: of)?|less than)\\s*" + NUM + "\\b(?!\\s*(?:km|kmpl|seat|cc|k\\b))"));
                if (m && +m[1] <= 100) return [null, +m[1] * 1e5];
                m = t.match(new RegExp("^\\s*" + NUM + "\\s*$"));
                if (m && +m[1] <= 100) return [null, +m[1] * 1e5];
                return [null, null];
            }
        }
        if (/(no|not)\s+(more than|above|over|beyond|exceeding)\s*$/.test(ctx)) return [null, val];
        if (/(around|about|approx\w*|roughly|near|nearly|close to)\s*$/.test(ctx)) return [val * 0.85, val * 1.15];
        if (/(above|over|more than|atleast|at least|minimum|min|starting|from|beyond)\s*$/.test(ctx) || /^\s*(\+|plus|and above|or more)/.test(after)) return [val, null];
        return [null, val];
    }

    const newPrefs = () => ({ budget: null, min_budget: null, fuels: [], exclude_fuels: [], transmission: null, seats: null, seats_exact: false, seats_target: null,
            body: null, exclude_bodies: [], brands: [], exclude_brands: [], similar: null, min_year: null, min_mileage: null,
            segment: [], soft_segment: [], soft_transmission: null, notes: [], extreme_more: [], body_in: [], prefer_body: [], ultra: false, offroad: false, easy_drive: false, extreme: null, soft_body: [], soft_fuel: [], use: null, performance_priority: false,
            mileage_priority: false, maintenance_priority: false, budget_priority: false, premium: false });

    function extract(text) {
        let t = " " + normalise(text) + " ";
        const p = newPrefs();
        const NOFUEL = /(zero|no|without)\s+(petrol|fuel|diesel)\s+(expenses?|costs?|bills?|spend\w*)|(petrol|fuel)[\s-]*free|zero\s+(petrol|fuel)/;
        if (NOFUEL.test(t)) { p.fuels.push("Electric"); t = t.replace(new RegExp(NOFUEL.source, "g"), " "); }
        if (ULTRA.test(t)) { p.ultra = true; p.premium = true; t = t.replace(new RegExp(ULTRA.source, "g"), " "); }
        const NOBUD = /(no|unlimited|any)\s+budget(\s+limit)?|money\s+(is\s+)?no\s+(issue|object|problem)/;
        if (NOBUD.test(t)) { p.premium = true; t = t.replace(new RegExp(NOBUD.source, "g"), " "); }
        const NOTEXP = /not\s+(too\s+|very\s+|so\s+)?(expensive|costly|pricey)/;
        if (NOTEXP.test(t)) { p.budget_priority = true; t = t.replace(new RegExp(NOTEXP.source, "g"), " "); }

        const original = t, found = [];
        for (const [name, pat] of EXTREMES) {
            const m = t.match(new RegExp(pat));
            if (m) {
                found.push([original.indexOf(m[0]), name]); t = t.replace(new RegExp(pat, "g"), " ");
                if (name === "price_desc") p.premium = true;
                else if (name === "price_asc") p.budget_priority = true;
                else if (name === "mileage_desc") p.mileage_priority = true;
                else if (name === "power_desc") p.performance_priority = true;
                else if (name === "seats_desc") p.seats_target = 8;
                else p.maintenance_priority = true;
            }
        }
        if (found.length) {
            found.sort((a, b) => a[0] - b[0] || (a[1] < b[1] ? -1 : a[1] > b[1] ? 1 : 0));
            p.extreme = found[0][1]; p.extreme_more = found.slice(1).map(x => x[1]);
        }
        const kind = w => has(FUEL_WORDS, w) ? "fuel" : ["automatic", "auto", "amt", "cvt", "manual"].includes(w) ? "gear" : has(BODY_WORDS, w) ? "body"
            : (has(BRANDS, w) || has(ORIGINS, w)) ? "brand" : null;
        const exclude = w => {
            const k = kind(w);
            if (k === "fuel") p.exclude_fuels.push(FUEL_WORDS[w]);
            else if (k === "gear") p.transmission = w === "manual" ? "Automatic" : "Manual";
            else if (k === "body") p.exclude_bodies.push(BODY_WORDS[w]);
            else (has(BRANDS, w) ? [BRANDS[w]] : ORIGINS[w]).forEach(b => { if (!p.exclude_brands.includes(b)) p.exclude_brands.push(b); });
        };
        t = t.replace(new RegExp("\\b" + NEG + "\\s+" + ITEM + "([a-z0-9]+)((?:\\s*(?:,|or|and|nor|&)\\s*" + ITEM + "[a-z0-9]+)*)", "g"), (m, first, rest) => {
            if (!kind(first)) return m;
            exclude(first);
            rest = rest || "";
            const re = new RegExp("\\s*(,|or|and|nor|&)\\s*" + ITEM + "([a-z0-9]+)", "g");
            let tm;
            while ((tm = re.exec(rest)) !== null) {
                const sep = tm[1], w = tm[2];
                // "or"/"nor" keep negating anything; "and"/"," only within the same kind ("no diesel, automatic" = no diesel, but do want automatic)
                if (kind(w) && (sep === "or" || sep === "nor" || kind(w) === kind(first))) exclude(w);
                else return " " + rest.slice(tm.index);
            }
            return " ";
        });
        const DC = [["mileage", "mileage_priority"], ["price", "budget_priority"], ["maintenance", "maintenance_priority"], ["performance", "performance_priority"]];
        for (const [w, key] of DC) {
            const re = new RegExp("don'?t care (?:about )?" + w);
            if (re.test(t)) { p[key] = null; t = t.replace(new RegExp(re.source, "g"), " "); }
        }

        [p.min_budget, p.budget] = budget(t);
        const toks = t.match(/[a-z0-9]+/g) || [];
        toks.forEach((w, i) => {
            (has(ORIGINS, w) ? ORIGINS[w] : []).forEach(b => { if (!p.brands.includes(b) && !p.exclude_brands.includes(b)) p.brands.push(b); });
            if (has(BRANDS, w) && !p.brands.includes(BRANDS[w]) && !p.exclude_brands.includes(BRANDS[w])) p.brands.push(BRANDS[w]);
            if (has(MODEL_KEY, w) && p.similar === null && !(AMBIGUOUS.has(w) && !(i && has(BRANDS, toks[i - 1])))) p.similar = MODEL_KEY[w];
            if (has(FUEL_WORDS, w) && !p.fuels.includes(FUEL_WORDS[w]) && !p.exclude_fuels.includes(FUEL_WORDS[w])) p.fuels.push(FUEL_WORDS[w]);
        });
        if (/\bgas\b/.test(t) && !p.fuels.includes("Petrol") && !p.exclude_fuels.includes("Petrol")) p.fuels.push("Petrol");
        if (/battery|zero emission/.test(t) && !p.fuels.includes("Electric")) p.fuels.push("Electric");
        if (/\beco|green|environment|pollution/.test(t) && !p.fuels.length) p.soft_fuel = ["Electric", "CNG", "Hybrid"];
        if (p.similar && p.brands.length === 1 && p.brands[0] === D.modelBrand[p.similar]) p.brands = [];

        if (p.transmission === null) {
            const auto = /\b(automatic|auto|amt|cvt|dct|dsg)\b|no gear|no clutch|clutchless|easy to drive|effortless|without clutch/.test(t);
            const manual = /\b(manual|stick)\b|gear shift/.test(t);
            if (auto && !manual) p.transmission = "Automatic"; else if (manual && !auto) p.transmission = "Manual";
        }
        const W = Object.keys(WORDS).join("|");
        let m = t.match(new RegExp("(\\d+|" + W + ")\\s*\\+?[\\s-]*(?:seater|seats?|seating|people|persons|passengers|members)")) || t.match(new RegExp("family of (\\d+|" + W + ")"));
        if (m) { p.seats = /^\d+$/.test(m[1]) ? +m[1] : WORDS[m[1]]; p.seats_exact = p.seats <= 2; }
        else if (/\b(big|large|joint|extended)\s+family|grandparents?|grandma|grandpa|in[\s-]?laws/.test(t)) p.seats = 7;
        else if (/family|kids|children|parents|\bwife\b|husband|\bkid\b/.test(t)) p.seats = 5;
        if (p.seats === null && p.seats_target === null && SPACE.test(t)) p.seats_target = 7;

        for (const w of toks) if (has(BODY_WORDS, w) && !p.exclude_bodies.includes(BODY_WORDS[w])) p.body = BODY_WORDS[w];

        m = t.match(new RegExp(NUM + "\\s*\\+?\\s*(?:km\\s*/\\s*l|kmpl|kpl|km per l\\w*|kilometre per litre)")) ||
            t.match(new RegExp("(?:mileage|average)\\D{0,15}?" + NUM + "(?!\\d)(?!\\s*(?:lakh|lac|l\\b|cr|seat|k\\b))"));
        if (m) { p.min_mileage = +m[1]; p.mileage_priority = true; }
        else if (/mileage|fuel efficient|fuel economy|economy|efficient|\baverage\b|save fuel|less fuel|fuel consumption|kmpl/.test(t)) p.mileage_priority = true;
        if (/\bfast|speed|powerful|\bpower\b|performance|sporty|quick|pickup|acceleration|torque/.test(t)) p.performance_priority = true;
        if (/maintenance|maintain|service cost|servicing|running cost|upkeep|cheap service|low service/.test(t)) p.maintenance_priority = true;
        if (/cheap|affordable|low budget|economical|value for money|sast[aei]|kam budget|pocket friendly|tight budget/.test(t)) p.budget_priority = true;
        if (/premium|luxur|expensive|high end|top end|executive|classy|impress|client|\bceo\b|\bboss\b|\brich\b|wealthy|prestige|show ?off|chauffeur/.test(t)) p.premium = true;
        if (/luxur/.test(t)) p.segment = ["Luxury"];
        else if (/premium|expensive|high end|top end|executive|classy|impress|client|\bceo\b|\bboss\b|\brich\b|wealthy|prestige|show ?off|chauffeur/.test(t)) p.soft_segment = ["Premium", "Luxury"];

        m = t.match(/(20[12]\d)\s*(?:model|or newer|and above|onwards|\+)/) || t.match(/(?:since|from|newer than)\s*(20[12]\d)/);
        if (m) p.min_year = +m[1];
        else if ((m = t.match(/after\s*(20[12]\d)/))) p.min_year = +m[1] + 1;
        else if (/latest|newest|new model|recent|brand new|newer|modern/.test(t)) p.min_year = 2023;

        let soft = [];
        if (p.similar === "City") t = t.replace(/\bcity\b/g, " ");
        if (/\bcity\b|traffic|parking|narrow|compact|\bsmall\b|tiny/.test(t)) {
            soft = ["Hatchback", "Sedan"]; p.use = "city driving";
            if (t.includes("traffic") && p.transmission === null) p.transmission = "Automatic";
        }
        if (/daily|commute|office|\bwork\b/.test(t)) { soft = ["Hatchback", "Sedan"]; p.use = "daily commute"; p.mileage_priority = true; }
        if (/first car|beginner|learner|new driver|student|college/.test(t)) { soft = ["Hatchback"]; p.use = "first car"; p.budget_priority = true; }
        if (/long drive|road trip|highway|touring|travel|outstation/.test(t)) { soft = ["Sedan", "SUV", "MPV"]; p.use = "long drives"; p.performance_priority = true; }
        if (OFFROAD.test(t)) { soft = ["SUV"]; p.use = "off-road driving"; p.offroad = true; }
        else if (SOFT_ROUGH.test(t)) { soft = ["SUV"]; p.use = "rough roads"; p.performance_priority = true; }
        if (/taxi|commercial|\bcab\b|fleet|\buber\b|\bola\b/.test(t)) { soft = ["Sedan", "MPV"]; p.use = "commercial use"; p.mileage_priority = true; p.maintenance_priority = true;
            if (!p.body) p.body_in = ["Sedan", "MPV"];
            if (!p.fuels.length) p.soft_fuel = ["CNG", "Diesel"]; }
        if (SPACE.test(t)) { soft = ["SUV", "MPV"]; p.use = "extra space"; }
        if (ELDERLY.test(t)) { soft = ["SUV", "MPV"]; p.use = "easy entry for elders"; p.prefer_body = ["MPV"]; if (p.transmission === null) p.soft_transmission = "Automatic"; p.notes.push(["Seat height", NOTE_TEXT.entry]); }
        if (NERVOUS.test(t)) { soft = ["Hatchback", "SUV"]; p.use = "confident, easy driving"; p.easy_drive = true; p.prefer_body = ["Hatchback"]; if (p.transmission === null) p.soft_transmission = "Automatic"; }
        if (LADIES.test(t)) { soft = ["Hatchback"]; p.use = "easy city driving"; if (p.transmission === null) p.soft_transmission = "Automatic"; }
        if (STYLISH.test(t)) { soft = ["SUV", "Coupe"]; p.use = "stylish looks"; p.notes.push(["Style", NOTE_TEXT.style]); }
        if (BIG_TYRES.test(t)) { soft = ["SUV"]; p.use = "bigger wheels"; p.notes.push(["Tyre size", NOTE_TEXT.tyres]); }
        if (SOUND.test(t)) {
            p.use = p.use || "premium audio";
            if (!p.segment.length && !p.soft_segment.length) p.soft_segment = ["Premium", "Luxury"];
            p.notes.push(["Sound system", NOTE_TEXT.sound]);
        }
        const cm = t.match(COLOUR);
        if (cm) p.notes.push([cm[1] ? `Colour (${cm[1]})` : "Colour", NOTE_TEXT.colour]);
        if (RATING.test(t)) p.notes.push(["Ratings", NOTE_TEXT.rating]);
        if (/supercar/.test(t)) { p.use = "sports driving"; p.performance_priority = true; if (!p.body) p.body = "Coupe"; }
        if (!p.body) p.soft_body = soft;
        ["performance_priority", "mileage_priority", "maintenance_priority", "budget_priority"].forEach(k => { p[k] = Boolean(p[k]); });
        return p;
    }


    /* ---------------- follow-ups ("cheaper", "only automatic", "bigger") ---------------- */
    const RESET = /\b(start over|start again|reset|new search|clear (all|everything)|forget (that|everything|it))\b/;
    const CHEAPER = /\b(cheaper|less expensive|lower (the )?(price|budget)|reduce (the )?budget|more affordable|budget[\s-]?friendly|lesser price)\b/;
    const PRICIER = /\b(more expensive|pricier|costlier|more premium|upgrade|step up|something better|higher end|better car)\b/;
    const RAISE = /\b(increase|raise|stretch|higher|bigger|more)\s+(the\s+)?budget\b|can spend more|afford more/;
    const BIGGER = /\b(bigger|larger|roomier|more space|more spacious|more seats|extra seats|more room)\b/;
    const SMALLER = /\b(smaller|more compact|tinier)\b/;
    const MORE_MILEAGE = /\b(more|better|higher|great|good)\s+(mileage|efficiency|fuel economy)\b|\bmore fuel efficient\b/;
    const DROP = /\b(remove|drop|ignore|forget|skip)\s+(?:the\s+)?(budget|brand|fuel|body|seats?|gearbox|transmission|mileage)\b/g;
    const DROP_KEYS = { budget: ["budget", "min_budget"], brand: ["brands", "exclude_brands"], fuel: ["fuels", "exclude_fuels"], body: ["body", "exclude_bodies", "soft_body", "body_in"],
        seat: ["seats", "seats_exact", "seats_target"], seats: ["seats", "seats_exact", "seats_target"], gearbox: ["transmission"], transmission: ["transmission"], mileage: ["min_mileage"] };
    const roundTo = (x, step) => Math.floor(x / step + 0.5) * step;
    const clone = o => JSON.parse(JSON.stringify(o));
    const differs = (a, b) => JSON.stringify(a) !== JSON.stringify(b);

    function refine(prev, text, refPrice) {
        const t = " " + text.toLowerCase() + " ";
        if (RESET.test(t)) return extract(text.toLowerCase().replace(new RegExp(RESET.source, "g"), " "));
        const nw = extract(text), base = newPrefs(), cur = Object.assign(newPrefs(), clone(prev));
        cur.notes = [];
        for (const [k, v] of Object.entries(nw)) {
            if (["exclude_fuels", "exclude_bodies", "exclude_brands"].includes(k)) cur[k] = [...cur[k], ...v.filter(x => !cur[k].includes(x))];
            else if (k === "notes") cur[k] = v;
            else if (differs(v, base[k])) cur[k] = clone(v);
        }
        if (nw.budget || nw.min_budget) { cur.budget = nw.budget; cur.min_budget = nw.min_budget; }
        if (nw.extreme) cur.extreme_more = nw.extreme_more;
        if (nw.seats) cur.seats_target = null;
        [["fuels", "exclude_fuels"], ["brands", "exclude_brands"]].forEach(([pos, neg]) => {
            cur[neg] = cur[neg].filter(x => !nw[pos].includes(x));
            cur[pos] = cur[pos].filter(x => !nw[neg].includes(x));
        });
        if (nw.body) cur.exclude_bodies = cur.exclude_bodies.filter(x => x !== nw.body);
        cur.exclude_bodies = cur.exclude_bodies.filter(x => x !== cur.body);
        if (cur.body) cur.soft_body = [];

        const ref = prev.budget || refPrice, spoken = Boolean(nw.budget || nw.min_budget);
        for (const m of t.matchAll(DROP)) DROP_KEYS[m[2]].forEach(key => { cur[key] = clone(base[key]); });
        if (CHEAPER.test(t) && !spoken) {
            if (ref) { cur.budget = roundTo(ref * (prev.extreme === "price_desc" ? 0.5 : 0.8), 1e4); cur.min_budget = null; }
            cur.budget_priority = true; cur.premium = false;
            if (cur.extreme === "price_desc") cur.extreme = null;
            if (differs(cur.soft_segment, ["Premium", "Luxury"]) === false) cur.soft_segment = [];
        } else if (PRICIER.test(t) && !spoken) {
            if (refPrice || ref) { const top = refPrice || ref; cur.min_budget = roundTo(top * 1.1, 1e4); cur.budget = roundTo(top * 2.2, 1e4); }
            cur.premium = true; cur.budget_priority = false;
            if (cur.extreme === "price_asc") cur.extreme = null;
        } else if (RAISE.test(t) && !spoken) {
            if (prev.budget) cur.budget = roundTo(prev.budget * 1.3, 1e4);
            else if (refPrice) cur.budget = roundTo(refPrice * 1.5, 1e4);
        }
        if (BIGGER.test(t) && !nw.seats) {
            if ((cur.seats || 0) < 7) { cur.seats = 7; cur.seats_exact = false; cur.seats_target = null; }
            else cur.seats_target = 8;
        }
        if (SMALLER.test(t)) {
            cur.seats = null; cur.seats_exact = false; cur.seats_target = null;
            if (!cur.body) cur.soft_body = ["Hatchback", "Sedan"];
        }
        if (MORE_MILEAGE.test(t)) {
            cur.mileage_priority = true;
            if (cur.min_mileage) cur.min_mileage = Math.floor(cur.min_mileage * 1.15 * 10 + 0.5) / 10;
        }
        return cur;
    }

    /* the browser hands back last search's preferences: keep only well-formed, known values (mirror of nlu.sanitize_prefs) */
    function sanitizePrefs(d) {
        const out = newPrefs();
        if (!d || typeof d !== "object") return out;
        const FU = ["Petrol", "Diesel", "Electric", "CNG", "Hybrid"], BO = ["SUV", "Sedan", "Hatchback", "MPV", "Coupe"], SE = ["Budget", "Mainstream", "Premium", "Luxury"];
        const lst = (v, ok) => Array.isArray(v) ? v.filter(x => typeof x === "string" && ok.includes(x)) : [];
        const num = (v, lo, hi) => typeof v === "number" && v >= lo && v <= hi ? v : null;
        out.budget = num(d.budget, 1, 1e10); out.min_budget = num(d.min_budget, 1, 1e10);
        out.min_mileage = num(d.min_mileage, 1, 100); out.seats_target = num(d.seats_target, 1, 9);
        out.seats = num(d.seats, 1, 9) ? Math.trunc(d.seats) : null; out.min_year = num(d.min_year, 2000, 2035) ? Math.trunc(d.min_year) : null;
        out.seats_exact = d.seats_exact === true;
        [["fuels", FU], ["exclude_fuels", FU], ["exclude_bodies", BO], ["soft_body", BO], ["brands", ALL_BRANDS], ["exclude_brands", ALL_BRANDS], ["segment", SE], ["soft_segment", SE], ["soft_fuel", FU]]
            .forEach(([k, ok]) => { out[k] = lst(d[k], ok); });
        out.transmission = ["Automatic", "Manual"].includes(d.transmission) ? d.transmission : null;
        out.soft_transmission = ["Automatic", "Manual"].includes(d.soft_transmission) ? d.soft_transmission : null;
        out.body = BO.includes(d.body) ? d.body : null;
        out.similar = D.models.includes(d.similar) ? d.similar : null;
        out.extreme = Object.keys(EXTREME_LABEL).includes(d.extreme) ? d.extreme : null;
        out.use = typeof d.use === "string" ? d.use.slice(0, 40) : null;
        out.extreme_more = Array.isArray(d.extreme_more) ? d.extreme_more.filter(x => Object.keys(EXTREME_LABEL).includes(x)) : [];
        out.body_in = lst(d.body_in, BO); out.prefer_body = lst(d.prefer_body, BO);
        ["ultra", "offroad", "easy_drive"].forEach(k => { out[k] = d[k] === true; });
        ["performance_priority", "mileage_priority", "maintenance_priority", "budget_priority", "premium"].forEach(k => { out[k] = d[k] === true; });
        return out;
    }

    function summarise(p) {
        const s = [];
        if (p.min_budget && p.budget) s.push(["Budget", `${money(p.min_budget)} – ${money(p.budget)}`]);
        else if (p.budget) s.push(["Budget", `Up to ${money(p.budget)}`]);
        else if (p.min_budget) s.push(["Budget", `From ${money(p.min_budget)}`]);
        if (p.brands.length) s.push(["Brand", p.brands.join(" / ")]);
        if (p.similar) s.push(["Like", p.similar]);
        if (p.fuels.length) s.push(["Fuel", p.fuels.join(" / ")]);
        if (p.transmission) s.push(["Gearbox", p.transmission]);
        if (p.seats) s.push(["Seats", p.seats_exact ? `${p.seats}` : `${p.seats}+`]);
        if (p.body) s.push(["Body", p.body]);
        if (p.min_mileage) s.push(["Mileage", `${p.min_mileage}+ km/l`]);
        if (p.min_year) s.push(["Year", `${p.min_year}+`]);
        if (p.body_in.length) s.push(["Body", p.body_in.join(" / ")]);
        if (p.ultra) s.push(["Tier", "Ultra-luxury"]); else if (p.segment.length) s.push(["Tier", p.segment.join(" / ")]);
        if (p.offroad) s.push(["Type", "Off-road capable"]);
        if (p.extreme) s.push(["Rank by", [p.extreme, ...p.extreme_more].map(k => EXTREME_LABEL[k]).join(" + ")]);
        const avoid = [...p.exclude_fuels, ...p.exclude_bodies, ...p.exclude_brands];
        if (avoid.length) s.push(["Avoid", avoid.join(", ")]);
        if (p.use) s.push(["Best for", p.use]);
        if (p.notes.length) s.push(["Not in data", p.notes.map(x => x[0]).join(", ")]);
        const prio = [["performance", "performance_priority"], ["mileage", "mileage_priority"], ["low maintenance", "maintenance_priority"], ["low price", "budget_priority"], ["premium", "premium"]].filter(([, k]) => p[k]).map(([n]) => n);
        if (prio.length && !p.extreme) s.push(["Priority", prio.join(", ")]);
        return s.map(([label, value]) => ({ label, value }));
    }

    /* ---------------- 1. hard filters ---------------- */
    function masks(p) {
        const out = [];
        if (p.ultra) out.push(["ultra-luxury tier", ["ultra"], c => c.Ultra_Luxury]);
        if (p.min_mileage) out.push(["mileage", ["min_mileage"], c => (p.fuels.includes("Electric") && c.Is_EV) || c.Mileage >= p.min_mileage]);
        if (p.min_year) out.push(["year", ["min_year"], c => c.Year >= p.min_year]);
        if (p.transmission) out.push(["transmission", ["transmission"], c => c.Transmission === p.transmission]);
        if (p.offroad) out.push(["off-road capability", ["offroad"], c => c.Offroad]);
        if (p.body || p.exclude_bodies.length || p.body_in.length) out.push(["body type", ["body", "exclude_bodies", "body_in"], c => (p.body ? c.Body_Type === p.body : true) && (p.body_in.length ? p.body_in.includes(c.Body_Type) : true) && !p.exclude_bodies.includes(c.Body_Type)]);
        if (p.seats) out.push(["seating", ["seats", "seats_exact"], c => p.seats_exact ? c.Seating_Capacity === p.seats : c.Seating_Capacity >= p.seats]);
        if (p.fuels.length || p.exclude_fuels.length) out.push(["fuel type", ["fuels", "exclude_fuels"], c => (p.fuels.length ? p.fuels.includes(c.Fuel_Type) : true) && !p.exclude_fuels.includes(c.Fuel_Type)]);
        if (p.segment.length) out.push(["luxury tier", ["segment"], c => p.segment.includes(c.Segment)]);
        if (p.brands.length || p.exclude_brands.length) out.push(["brand", ["brands", "exclude_brands"], c => (p.brands.length ? p.brands.includes(c.Brand) : true) && !p.exclude_brands.includes(c.Brand)]);
        if (p.min_budget) out.push(["minimum price", ["min_budget"], c => c.Price >= p.min_budget]);
        if (p.budget) out.push(["budget", ["budget"], c => c.Price <= p.budget]);
        return out;
    }

    /* ---------------- 2. ranking ---------------- */
    function weights(p) {
        const askedSeats = Boolean(p.seats || p.seats_target || p.similar);
        if (p.performance_priority) return [.15, .05, .45, .20, .15];
        if (p.ultra) return [.55, .05, .20, .10, .10];
        if (p.offroad && !askedSeats) return [.40, .25, .10, .25, .0];
        if (p.mileage_priority) return [.15, .45, .15, .15, .10];
        if (p.maintenance_priority) return [.20, .15, .10, .45, .10];
        if (p.easy_drive) return [.30, .20, .25, .15, .10];
        if (p.budget_priority) return [.45, .15, .10, .20, .10];
        if (askedSeats) return [.30, .20, .10, .15, .25];
        return [.35, .25, .10, .20, .10];
    }
    const EXTREME_METRIC = { price_desc: ["Price", "max"], price_asc: ["Price", "min"], mileage_desc: ["Mileage", "max"], power_desc: ["Power_bhp", "max"], seats_desc: ["Seating_Capacity", "max"], service_asc: ["Service_Cost", "min"] };
    const EXTREME_REASON = { price_desc: "Among the most expensive matches", price_asc: "Among the lowest-priced matches", mileage_desc: "Top mileage in this search",
        power_desc: "Most powerful in this search", seats_desc: "Most seating in this search", service_asc: "Lowest running cost in this search" };
    const EXTREME_BAR = { price_desc: "Price fit", price_asc: "Price fit", mileage_desc: "Efficiency", power_desc: "Power", seats_desc: "Seating", service_asc: "Running cost" };

    function idealCar(df, p) {
        const pool = p.mass_market && df.some(c => c.Segment !== "Luxury") ? df.filter(c => c.Segment !== "Luxury") : df;
        const q = (k, x) => quantile(pool.map(c => c[k]), x);
        const cheap = p.budget_priority && !p.performance_priority, luxuryOnly = p.segment.length > 0;
        let price;
        if (p.budget) { price = p.budget * (cheap ? .6 : p.premium ? .95 : .85); if (p.min_budget) price = Math.max(price, p.min_budget); }
        else price = q("Price", cheap ? .05 : p.ultra ? .9 : p.premium ? (luxuryOnly ? .5 : .7) : .5);
        const target = { Price: price, Cost_Per_Km: p.min_mileage ? 100 / p.min_mileage : q("Cost_Per_Km", p.mileage_priority ? .15 : .5),
            Power_bhp: q("Power_bhp", p.performance_priority ? .8 : p.easy_drive ? .25 : p.premium ? .7 : .5), Service_Cost: q("Service_Cost", p.maintenance_priority ? .15 : p.premium ? .7 : .5),
            Seating_Capacity: p.seats || p.seats_target || q("Seating_Capacity", .5) };
        const side = { Price: "both", Cost_Per_Km: p.mileage_priority || cheap ? "lower" : "both",
            Power_bhp: p.performance_priority ? "higher" : (cheap || p.easy_drive) ? "lower" : "both", Service_Cost: p.maintenance_priority || cheap ? "lower" : "both",
            Seating_Capacity: p.prefer_body.includes("MPV") ? "higher" : "both" };
        if (p.similar) {
            const ref = cars.filter(c => c.Model === p.similar);
            const keep = { Price: p.budget || p.budget_priority || p.premium, Cost_Per_Km: p.min_mileage || p.mileage_priority, Power_bhp: p.performance_priority,
                Service_Cost: p.maintenance_priority, Seating_Capacity: p.seats || p.seats_target };
            FEATURES.forEach(k => { if (!keep[k]) { target[k] = median(ref.map(c => c[k])); side[k] = "both"; } });
        }
        return { target, side };
    }
    function balancedDistance(df, p) {
        const { target, side } = idealCar(df, p), w = weights(p);
        const d = df.map(c => Math.sqrt(FEATURES.reduce((a, k, j) => {
            let x = T(k, c[k]); const goal = T(k, target[k]);
            if (side[k] === "lower") x = Math.max(x, goal); else if (side[k] === "higher") x = Math.min(x, goal);
            return a + w[j] * ((x - goal) / SD[k]) ** 2;
        }, 0)));
        return { d, target, side };
    }
    function rank(df, p) {
        let { d, target, side } = balancedDistance(df, p);
        if (p.extreme) {
            const gap = new Array(df.length).fill(0);
            [p.extreme, ...p.extreme_more].forEach(name => {      // every named quality counts
                let [col, how] = EXTREME_METRIC[name];
                if (col === "Mileage" && ((p.fuels.length === 1 && p.fuels[0] === "Electric") || df.every(c => c.Mileage === null))) col = "Range_km";
                const vals = df.map(c => c[col]).filter(v => v !== null);
                const best = how === "max" ? Math.max(...vals) : Math.min(...vals);
                df.forEach((c, i) => { gap[i] += c[col] === null ? 5.0 : Math.abs(T(col, c[col]) - T(col, best)) / (SD[col] || 1); });
            });
            d = df.map((c, i) => gap[i] + 0.03 * d[i]);
        }
        const dist = df.map((c, i) => {
            let x = d[i];
            if (p.soft_body.length && !p.soft_body.includes(c.Body_Type)) x += SOFT_PENALTY;
            if (p.prefer_body.length && !p.prefer_body.includes(c.Body_Type)) x += PREFER_PENALTY;
            if (p.soft_fuel.length && !p.soft_fuel.includes(c.Fuel_Type)) x += SOFT_PENALTY;
            if (p.soft_segment.length && !p.soft_segment.includes(c.Segment)) x += SOFT_PENALTY;
            if (p.soft_transmission && c.Transmission !== p.soft_transmission) x += SOFT_PENALTY;
            if (!p.extreme) x += RECENCY_PENALTY * (LATEST_YEAR - c.Year);
            return x;
        });
        if (p.similar) {   // the model the user named always leads its own look-alikes
            const others = dist.filter((_, i) => df[i].Model !== p.similar);
            if (others.length && others.length < dist.length) {
                const floor = Math.min(...others) * 0.9;
                dist.forEach((x, i) => { if (df[i].Model === p.similar) dist[i] = Math.min(x * 0.25, floor); });
            }
        }
        const scored = df.map((c, i) => ({ c, pos: i, score: 100 * Math.exp(-SCORE_SHARPNESS * dist[i]) }))
            .sort((a, b) => b.score - a.score || a.pos - b.pos);
        return { scored, target, side };
    }

    /* ---------------- 3. presentation ---------------- */
    function explain(c, p, df) {
        const ev = c.Is_EV, good = [], warn = [];
        if (p.extreme) [p.extreme, ...p.extreme_more].forEach(n => good.push(EXTREME_REASON[n]));
        if (p.ultra) (c.Ultra_Luxury ? good : warn).push(c.Ultra_Luxury ? "Ultra-luxury tier" : "Not in the ultra-luxury tier");
        if (p.offroad) (c.Offroad ? good : warn).push(c.Offroad ? "Built for off-road use" : "Not a dedicated off-roader");
        if (p.body_in.length) (p.body_in.includes(c.Body_Type) ? good : warn).push(p.body_in.includes(c.Body_Type) ? `${c.Body_Type} - the usual choice for fleets` : c.Body_Type);
        if (p.soft_transmission && c.Transmission === p.soft_transmission) good.push(`${c.Transmission} - easy to drive`);
        if (p.similar && c.Model === p.similar) good.push("The model you asked about");
        else if (p.similar) good.push(`Similar to the ${p.similar}`);
        if (p.brands.length) { if (p.brands.includes(c.Brand)) good.push(c.Brand); else warn.push(`${c.Brand}, not ${p.brands.join("/")}`); }
        if (p.segment.length) { if (p.segment.includes(c.Segment)) good.push("Luxury segment"); else warn.push("Not a luxury model"); }
        if (p.budget) { const spare = p.budget - c.Price; if (spare < 0) warn.push("Above your budget"); else good.push(spare >= 5e4 ? `${money(spare)} under budget` : "Within your budget"); }
        else if (p.min_budget) (c.Price >= p.min_budget ? good : warn).push(`Priced at ${money(c.Price)}`);
        if (p.fuels.length) { if (p.fuels.includes(c.Fuel_Type)) good.push(`${c.Fuel_Type} as requested`); else warn.push(`${c.Fuel_Type}, not ${p.fuels.join("/")}`); }
        if (p.exclude_fuels.includes(c.Fuel_Type)) warn.push(`${c.Fuel_Type} (you wanted to avoid it)`);
        if (p.transmission) (c.Transmission === p.transmission ? good : warn).push(`${c.Transmission} gearbox`);
        if (p.body) { if (c.Body_Type === p.body) good.push(c.Body_Type); else warn.push(`${c.Body_Type}, not ${p.body}`); }
        if (p.seats) (p.seats_exact ? c.Seating_Capacity === p.seats : c.Seating_Capacity >= p.seats) ? good.push(`${c.Seating_Capacity} seats`) : warn.push(`${c.Seating_Capacity} seats`);
        if (p.min_year) (c.Year >= p.min_year ? good : warn).push(`${c.Year} model`);
        if (p.use && p.soft_body.length && p.soft_body.includes(c.Body_Type)) good.push(`Suits ${p.use}`);
        if (p.mileage_priority && !p.extreme) {
            if (ev) good.push(`Electric - about ₹${c.Cost_Per_Km.toFixed(1)}/km to run`);
            else if (c.Cost_Per_Km <= median(df.map(x => x.Cost_Per_Km))) good.push(`Good mileage: ${num2(c.Mileage)} km/l`);
        }
        if (p.min_mileage && !ev && c.Mileage < p.min_mileage) warn.push(`Only ${num2(c.Mileage)} km/l`);
        if (p.performance_priority && !p.extreme && c.Power_bhp >= quantile(df.map(x => x.Power_bhp), .6)) good.push(`Strong ${Math.trunc(c.Power_bhp)} bhp`);
        if (p.maintenance_priority && !p.extreme && c.Service_Cost <= quantile(df.map(x => x.Service_Cost), .4)) good.push(`Low service cost (₹${inr(c.Service_Cost)})`);
        if (p.premium && !p.extreme && !p.segment.length && c.Price >= quantile(df.map(x => x.Price), .7)) good.push("Premium pricing tier");
        return [good.length ? good : ["Well-balanced overall match"], warn];
    }

    function recommend(p, topN = 5) {
        const ms = masks(p);
        let dropped = [], df = cars;
        for (let k = 0; k <= ms.length; k++) {
            dropped = ms.slice(0, k);
            df = cars.filter(c => ms.slice(k).every(m => m[2](c)));
            if (df.length) break;
        }
        if ([p.extreme, ...p.extreme_more].includes("mileage_desc") && !p.fuels.includes("Electric") && df.some(c => !c.Is_EV)) df = df.filter(c => !c.Is_EV);
        const used = { ...p };
        dropped.forEach(([, keys]) => keys.forEach(key => { used[key] = Array.isArray(p[key]) ? [] : typeof p[key] === "boolean" ? false : null; }));
        used.mass_market = !(p.premium || p.segment.length || p.soft_segment.length || p.brands.length || p.similar || p.extreme || p.min_budget || (p.budget && p.budget > 50e5));
        if (used.mass_market) used.soft_segment = ["Budget", "Mainstream", "Premium"];
        const { scored, target, side } = rank(df, used);

        const fit = (k, x) => {
            const v = T(k, x), goal = T(k, target[k]);
            if ((side[k] === "lower" && v < goal) || (side[k] === "higher" && v > goal)) return 100;
            return Math.floor(100 * Math.exp(-Math.abs(v - goal) / SD[k]) + 0.5);
        };
        const variant = s => {
            const c = s.c, ev = c.Is_EV, [reasons, caveats] = explain(c, p, df);
            let bars = [{ label: "Price fit", fit: fit("Price", c.Price) }, { label: "Efficiency", fit: fit("Cost_Per_Km", c.Cost_Per_Km) },
                { label: "Power", fit: fit("Power_bhp", c.Power_bhp) }, { label: "Running cost", fit: fit("Service_Cost", c.Service_Cost) },
                { label: "Seating", fit: fit("Seating_Capacity", c.Seating_Capacity) }];
            if (p.extreme) { const keep = new Set([p.extreme, ...p.extreme_more].map(k => EXTREME_BAR[k])); bars = bars.filter(b => keep.has(b.label)); }
            return { year: c.Year, price: c.Price, mileage: ev ? null : c.Mileage, range_km: ev ? c.Range_km : null, engine_cc: c.Engine_CC, power_hp: c.Power_bhp,
                fuel_type: c.Fuel_Type, transmission: c.Transmission, seating_capacity: c.Seating_Capacity, service_cost: c.Service_Cost, cost_per_km: c.Cost_Per_Km,
                recommendation_score: Math.round(s.score * 10) / 10, reasons: reasons.slice(0, 5), caveats, breakdown: bars };
        };

        const cap = (p.brands.length || p.similar || p.extreme || p.offroad) ? 99 : p.ultra ? 1 : MAX_PER_BRAND;
        const picked = [], perBrand = {}, seen = new Set();
        for (const s of scored) {
            const key = s.c.Brand + "|" + s.c.Model;
            if (seen.has(key) || (perBrand[s.c.Brand] || 0) >= cap) continue;
            seen.add(key); perBrand[s.c.Brand] = (perBrand[s.c.Brand] || 0) + 1; picked.push(s.c);
            if (picked.length === topN) break;
        }
        if (picked.length < topN) {   // too few other brands to honour the mix: fill the rest by rank
            for (const s of scored) {
                const key = s.c.Brand + "|" + s.c.Model;
                if (seen.has(key)) continue;
                seen.add(key); picked.push(s.c);
                if (picked.length === topN) break;
            }
        }
        const recs = picked.map(c => {
            const combos = new Set(), vs = [];
            for (const s of scored) {
                if (s.c.Brand !== c.Brand || s.c.Model !== c.Model) continue;
                const k = s.c.Fuel_Type + "|" + s.c.Transmission;
                if (combos.has(k)) continue;
                combos.add(k); vs.push(variant(s));
                if (vs.length === 4) break;
            }
            const img = (D.images || {})[`${c.Brand}_${c.Model}`.replace(/ /g, "_").toLowerCase()];
            return { brand: c.Brand, model: c.Model, body_type: c.Body_Type, segment: c.Segment, image_url: img ? "/car-images/" + img : "", ...vs[0], variants: vs };
        });
        const notice = dropped.length ? "No car matched everything you asked for, so we loosened: " + dropped.map(d => d[0]).join(", ") + ". These are the closest matches." : null;
        return { notice, relaxed: dropped.map(d => d[0]), stats: { listings: cars.length, matched: df.length, models: new Set(df.map(c => c.Model)).size }, recommendations: recs };
    }

    /* ---------------- optional AI reading (same contract as llm.py) ---------------- */
    window.sanitizeAi = function (d) {
        if (!d || typeof d !== "object") return null;
        const FU = ["Petrol", "Diesel", "Electric", "CNG", "Hybrid"], BO = ["SUV", "Sedan", "Hatchback", "MPV", "Coupe"];
        const list = (v, ok) => Array.isArray(v) ? v.filter(x => ok.includes(x)) : [];
        const num = v => typeof v === "number" && v > 0 ? v : null, out = {};
        if (num(d.budget_max_lakh)) out.budget = d.budget_max_lakh * 1e5;
        if (num(d.budget_min_lakh)) out.min_budget = d.budget_min_lakh * 1e5;
        [["fuels", FU], ["exclude_fuels", FU], ["exclude_bodies", BO], ["brands", ALL_BRANDS], ["exclude_brands", ALL_BRANDS]].forEach(([k, ok]) => { if (list(d[k], ok).length) out[k] = list(d[k], ok); });
        if (["Automatic", "Manual"].includes(d.transmission)) out.transmission = d.transmission;
        if (BO.includes(d.body)) out.body = d.body;
        if (D.models.includes(d.similar_model)) out.similar = d.similar_model;
        if (num(d.seats_min) && d.seats_min >= 2 && d.seats_min <= 8) { out.seats = Math.floor(d.seats_min); out.seats_exact = out.seats <= 2; }
        if (num(d.min_mileage)) out.min_mileage = d.min_mileage;
        if (num(d.min_year) && d.min_year >= 2000 && d.min_year <= 2030) out.min_year = Math.floor(d.min_year);
        if (d.luxury === true) out.segment = ["Luxury"];
        if (Object.keys(EXTREME_LABEL).includes(d.rank_by)) out.extreme = d.rank_by;
        const PM = { performance: "performance_priority", mileage: "mileage_priority", maintenance: "maintenance_priority", low_price: "budget_priority", premium: "premium" };
        list(d.priorities, Object.keys(PM)).forEach(k => { out[PM[k]] = true; });
        if (typeof d.best_for === "string" && d.best_for.trim()) out.use = d.best_for.trim().slice(0, 30);
        return Object.keys(out).length ? out : null;
    };
    window.AI_PROMPT = `You convert a car-shopping request (any wording, any language, typos allowed) into JSON for a search engine.
Reply with ONE JSON object and nothing else. Omit keys you are unsure about. Keys:
budget_max_lakh (number), budget_min_lakh (number), fuels (list of Petrol/Diesel/Electric/CNG/Hybrid), exclude_fuels (same),
transmission (Automatic|Manual), seats_min (integer 2-8), body (SUV|Sedan|Hatchback|MPV|Coupe), exclude_bodies (list),
brands (list of: ${ALL_BRANDS.join(", ")}), exclude_brands (same), similar_model (one of: ${D.models.join(", ")}), min_mileage (km/l number), min_year (integer),
luxury (true when they want a luxury brand), rank_by (one of: price_desc, price_asc, mileage_desc, power_desc, seats_desc, service_asc
- use when they ask for the most expensive / cheapest / best mileage / fastest / biggest / lowest-maintenance car),
priorities (list from: performance, mileage, maintenance, low_price, premium), best_for (2-3 words).`;

    const NO_CLUE = "I could not pick out a specific requirement from that, so these are well-rounded popular picks. Try adding a budget, fuel, seats or body type.";
    window.localRecommend = function (query, ai, previous, refPrice) {
        const follow = previous !== undefined && previous !== null;
        const prev = follow ? sanitizePrefs(previous) : null;
        const p = follow ? refine(prev, query, refPrice) : extract(query);
        if (ai && !follow) Object.assign(p, ai);
        if (p.similar) {
            if (!p.body && !p.soft_body.length) p.soft_body = [D.body[p.similar] || "Other"];
            if (!p.segment.length && !p.soft_segment.length) p.soft_segment = [D.segment[p.similar]];
        }
        const result = recommend(p);
        const summary = summarise(p);
        if (p.notes.length) result.notice = [result.notice, ...p.notes.map(x => x[1])].filter(Boolean).join(" ");
        if (!summary.length && !ai) result.notice = NO_CLUE;
        const before = follow ? summarise(prev).map(s => JSON.stringify(s)) : [];
        const changes = follow ? summary.filter(s => !before.includes(JSON.stringify(s))) : [];
        return { success: true, message: "ok", ai: Boolean(ai && !follow), refined: follow, changes, summary, understood_preferences: p, ...result };
    };
})();
