/* AutoMind AI – frontend */

// Same-origin when served by FastAPI; talk to the local API when opened as a file or from a dev server.
const API_BASE = window.API_BASE ?? (
    location.protocol === "file:" ||
    (["localhost", "127.0.0.1"].includes(location.hostname) && location.port && location.port !== "8000")
        ? "http://127.0.0.1:8000" : ""
);
const REQUEST_TIMEOUT_MS = 45000;

const $ = id => document.getElementById(id);
const el = {
    form: $("searchForm"), input: $("searchInput"), button: $("searchButton"), buttonText: $("buttonText"),
    hint: $("searchHint"), section: $("resultsSection"), title: $("resultsTitle"),
    loading: $("loadingState"), loadingText: $("loadingText"), error: $("errorState"), errorMsg: $("errorMessage"),
    empty: $("noResultsState"), results: $("resultsContent"), notice: $("noticeBanner"),
    prefs: $("preferencesContainer"), cars: $("recommendationsContainer"),
    again: $("searchAgainButton"), retry: $("retryButton"), startOver: $("startOverButton"),
    menu: $("mobileMenu"), nav: $("navLinks"),
};

const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
let lastQuery = "", requestId = 0, controller = null, slowTimer = null;
let lastPrefs = null, lastRef = null, lastJob = null, trail = [];   // what the last search understood, so follow-ups can refine it

const esc = v => Object.assign(document.createElement("div"), { textContent: String(v ?? "") }).innerHTML;
const num = v => (v === null || v === undefined || Number.isNaN(Number(v))) ? null : Number(v);

function price(v) {
    const n = num(v);
    if (n === null) return "N/A";
    if (n >= 1e7) return `₹${+(n / 1e7).toFixed(2)} crore`;
    return n >= 1e5 ? `₹${+(n / 1e5).toFixed(2)} lakh` : "₹" + n.toLocaleString("en-IN");
}

const rupees = n => "₹" + Math.round(n).toLocaleString("en-IN");

/* ---------- ownership cost: EMI, fuel, service and 5-year total ---------- */
const ownKm = $("kmInput"), ownDown = $("downInput"), ownHint = $("ownHint");
const ownState = { ok: true, km: 30, down: null };
const ownOf = v => ownState.ok ? window.Ownership.ownershipCost(v, ownState.km, ownState.down) : null;

function ownHTML(v) {
    const o = ownOf(v);
    if (!o) return `<div class="own-empty">Enter your daily distance above to see the EMI and 5-year cost.</div>`;
    const ev = v.fuel_type === "Electric";
    return `<div class="own-grid" role="group" aria-label="Ownership cost">
        <div class="own-cell"><span>Monthly EMI</span><b>${o.hasLoan ? rupees(o.emi) : "No loan"}</b><small>${o.hasLoan ? `on a ${price(o.loan)} loan` : "paid upfront"}</small></div>
        <div class="own-cell"><span>${ev ? "Electricity" : "Fuel"} / month</span><b>${rupees(o.fuelMonthly)}</b><small>${+ownState.km.toFixed(1)} km a day</small></div>
        <div class="own-cell"><span>Service / year</span><b>${rupees(o.service)}</b><small>estimate</small></div>
        <div class="own-cell own-total"><span>Total 5-year cost</span><b>${price(o.total)}</b></div>
    </div>`;
}

function readOwnInputs() {
    const kmRaw = ownKm.value.trim(), downRaw = ownDown.value.trim();
    const km = kmRaw === "" ? NaN : Number(kmRaw);
    const down = downRaw === "" ? null : Number(downRaw) * 1e5;
    const kmBad = !(km > 0 && km <= window.Ownership.MAX_KM_PER_DAY);
    const downBad = down !== null && !(down >= 0);
    ownKm.setAttribute("aria-invalid", String(kmBad));
    ownDown.setAttribute("aria-invalid", String(downBad));
    ownHint.textContent = kmBad ? "Enter a daily distance between 1 and 500 km." : downBad ? "Down payment can't be negative." : "";
    Object.assign(ownState, { ok: !kmBad && !downBad, km, down });
}

const refreshOwnership = () => { readOwnInputs(); [...el.cars.children].forEach(c => c._own && c._own()); };
$("ownForm").addEventListener("submit", e => e.preventDefault());
ownKm.addEventListener("input", refreshOwnership);
ownDown.addEventListener("input", refreshOwnership);
readOwnInputs();

/* Neutral placeholder for cars without a real photo (no wrong or broken web images). */
function placeholder(brand, model) {
    const hue = [...brand].reduce((a, c) => a + c.charCodeAt(0), 0) * 7 % 360;
    const svg = `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 400 150'>

<g fill='hsl(${hue},70%,72%)' fill-opacity='.28'><path d='M92 100 L108 76 Q115 67 128 67 H264 Q278 67 286 78 L306 100 Q320 102 320 114 V120 H80 V114 Q80 102 92 100Z'/></g>
<g fill='#0c0d0f' stroke='#fff' stroke-opacity='.25' stroke-width='3'><circle cx='128' cy='120' r='16'/><circle cx='272' cy='120' r='16'/></g>
<text x='200' y='142' text-anchor='middle' font-family='Arial' font-size='11' fill='#fff' fill-opacity='.45'>${esc(brand)} ${esc(model)}</text></svg>`;
    return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
}


/* ---------- car photos ----------
   Order: photo in /car_images  ->  your own link in image-links.js  ->  Wikipedia lead photo (verified by title)  ->  placeholder */
const IMG_KEY = "automind.img.v3";
const imgCache = (() => { try { return JSON.parse(localStorage.getItem(IMG_KEY)) || {}; } catch { return {}; } })();
const saveImgCache = () => { try { localStorage.setItem(IMG_KEY, JSON.stringify(imgCache)); } catch { /* storage unavailable */ } };
const norm = t => t.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]/g, "");
const MODEL_ALT = { Jazz: ["jazz", "fit"] };
const BRAND_ALT = { "Maruti Suzuki": ["maruti", "suzuki"], Renault: ["renault", "dacia"], "Tata Motors": ["tata"] };
const SEARCH_BRAND = { "Tata Motors": "Tata" };
const inflight = {};

function findCarImage(brand, model) {
    const key = `${brand} ${model}`;
    const manual = window.CAR_IMAGE_LINKS && window.CAR_IMAGE_LINKS[key];
    if (manual) return Promise.resolve({ url: manual, credit: "" });
    if (key in imgCache) return Promise.resolve(imgCache[key]);
    if (inflight[key]) return inflight[key];

    inflight[key] = (async () => {
        const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 8000);
        try {
            const url = "https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrlimit=6&prop=pageimages&piprop=thumbnail&pithumbsize=900&format=json&origin=*&gsrsearch="
                + encodeURIComponent(`${SEARCH_BRAND[brand] || brand} ${model}`);
            const res = await fetch(url, { signal: ctl.signal });
            const pages = Object.values((await res.json()).query?.pages || {}).sort((a, b) => a.index - b.index);
            const models = (MODEL_ALT[model] || [model]).map(norm);
            const brands = (BRAND_ALT[brand] || [brand]).map(norm);
            const hit = pages.find(p => p.thumbnail && models.some(m => norm(p.title).includes(m)) && brands.some(b => norm(p.title).includes(b)));
            const out = hit ? { url: hit.thumbnail.source, credit: "Photo: Wikipedia", page: "https://en.wikipedia.org/wiki/" + encodeURIComponent(hit.title.replace(/ /g, "_")) } : null;
            imgCache[key] = out; saveImgCache();
            return out;
        } catch { return null; }                       // network problem: don't cache, try again next time
        finally { clearTimeout(timer); delete inflight[key]; }
    })();
    return inflight[key];
}

/* ---------- view state ---------- */
function show(state) {
    el.section.classList.remove("hidden");
    for (const [name, node] of Object.entries({ loading: el.loading, error: el.error, empty: el.empty, results: el.results })) {
        node.classList.toggle("hidden", name !== state);
    }
    el.again.classList.toggle("hidden", state === "loading");
    el.section.setAttribute("aria-busy", String(state === "loading"));
    const busy = state === "loading";
    el.button.disabled = busy;
    el.buttonText.textContent = busy ? "Searching..." : "Find My Car";
}

function goToResults() {
    el.section.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
}

function showError(message) {
    el.errorMsg.textContent = message;
    show("error");
}

function setHint(message) {
    el.hint.textContent = message || "";
    el.hint.classList.toggle("hidden", !message);
    el.input.setAttribute("aria-invalid", String(Boolean(message)));
}

/* ---------- rendering ---------- */
const lakhTxt = v => v >= 1e7 ? "₹" + +(v / 1e7).toFixed(2) + " crore" : "₹" + +(v / 1e5).toFixed(2) + " lakh";
const agent = Object.assign(document.createElement("div"), { id: "agentBubble", className: "agent" });
const followBox = Object.assign(document.createElement("div"), { id: "followups", className: "followups" });
el.results.prepend(agent);
el.cars.insertAdjacentElement("afterend", followBox);

/* One friendly sentence describing how the request was understood. */
function agentSentence(p) {
    const EXT = { price_desc: "most expensive", price_asc: "cheapest", mileage_desc: "most fuel-efficient", power_desc: "most powerful", seats_desc: "roomiest", service_asc: "cheapest-to-run" };
    const adj = [...(p.ultra ? ["ultra-luxury"] : (p.segment || []).map(x => x.toLowerCase())), ...(p.offroad ? ["off-road"] : []), ...(p.fuels || []).map(f => f.toLowerCase()), ...(p.transmission ? [p.transmission.toLowerCase()] : [])];
    const core = [...adj, (p.brands || []).join("/"), p.body || (p.body_in || []).join("/").toLowerCase() || "car"].filter(Boolean).join(" ");
    const tail = [];
    if (p.seats) tail.push(`${p.seats}+ seats`);
    if (p.min_budget && p.budget) tail.push(`between ${lakhTxt(p.min_budget)} and ${lakhTxt(p.budget)}`);
    else if (p.budget) tail.push(`under ${lakhTxt(p.budget)}`);
    else if (p.min_budget) tail.push(`from ${lakhTxt(p.min_budget)}`);
    if (p.min_mileage) tail.push(`${p.min_mileage}+ km/l`);
    else if (p.mileage_priority && !p.extreme) tail.push("great mileage");
    if (p.performance_priority && !p.extreme) tail.push("strong performance");
    if (p.maintenance_priority && !p.extreme) tail.push("low running costs");
    if (p.min_year) tail.push(`${p.min_year} or newer`);
    if (p.use) tail.push(`good for ${p.use}`);
    const avoid = [...(p.exclude_fuels || []), ...(p.exclude_bodies || []), ...(p.exclude_brands || [])];
    if (avoid.length) tail.push(`no ${avoid.join("/").toLowerCase()}`);
    if (!p.similar && !p.extreme && !tail.length && core === "car") return "Here are all-rounders to start with. Tell me what matters most and I'll tune them.";
    const lead = p.extreme ? `the ${[p.extreme, ...(p.extreme_more || [])].map(k => EXT[k]).join(" and ")} ${core}s`
        : p.similar ? `something like the ${p.similar}` : `${/^[aeiou]/i.test(core) ? "an" : "a"} ${core}`;
    return `Got it — you're after ${lead}${tail.length ? ", " + tail.join(", ") : ""}. Here are my best matches.`;
}

/* Message shown after a follow-up such as "cheaper": say exactly what changed. */
function refineSentence(data) {
    const ch = data.changes || [];
    return ch.length ? `Updated — ${ch.map(c => `${c.label}: ${c.value}`).join(" · ")}. Here are the new matches.`
        : "I couldn't find anything new to change in that, so these are the same matches. Try “cheaper”, “only automatic” or “no diesel”.";
}

/* Quick replies for whatever the request has not said yet, plus ways to refine. */
function followUps(p) {
    const g = [];
    if (!p.budget && !p.min_budget) g.push(["Budget", [["Under ₹8 lakh", "under 8 lakh"], ["₹8–15 lakh", "8 to 15 lakh"], ["₹15–25 lakh", "15 to 25 lakh"], ["₹25 lakh–1 crore", "25 lakh to 1 crore"], ["₹1 crore+", "above 1 crore"]]]);
    if (!(p.fuels || []).length && !(p.exclude_fuels || []).length) g.push(["Fuel", ["Petrol", "Diesel", "Electric", "CNG"].map(x => [x, x.toLowerCase()])]);
    if (!p.seats) g.push(["Seats", [["5 seater", "5 seater"], ["7 seater", "7 seater"]]]);
    if (!p.transmission) g.push(["Gearbox", [["Automatic", "automatic"], ["Manual", "manual"]]]);
    return [...g.slice(0, 2), ["Refine", [["Cheaper", "cheaper"], ["More expensive", "more expensive"], ["Bigger", "bigger"], ["Better mileage", "more mileage"], ["More powerful", "more powerful"], ["Newer", "newer model"]]]];
}

function renderPreferences(summary) {
    el.prefs.innerHTML = (summary?.length ? summary : [{ label: "Search", value: "All-round picks" }])
        .map(s => `<div class="preference"><span class="preference-label">${esc(s.label)}</span>
            <span class="preference-value">${esc(s.value)}</span></div>`).join("");
}

function spec(label, value) {
    return `<div class="spec"><span class="spec-label">${label}</span><span class="spec-value">${esc(value)}</span></div>`;
}

const RING = 2 * Math.PI * 18;
function setRing(card, score) {
    const ring = card.querySelector(".ring"), n = Math.round(score ?? 0);
    ring.className = "ring " + (n >= 80 ? "great" : n >= 60 ? "good" : "fair");
    ring.setAttribute("aria-label", `Match score ${n} percent`);
    const fg = ring.querySelector(".ring-fg"), num = ring.querySelector(".ring-num");
    requestAnimationFrame(() => { fg.style.strokeDashoffset = String(RING * (1 - n / 100)); });
    if (reduceMotion) { num.textContent = n + "%"; return; }
    const t0 = performance.now();
    (function tick(t) {
        const k = Math.min(1, (t - t0) / 800);
        num.textContent = Math.round(n * (1 - (1 - k) ** 3)) + "%";
        if (k < 1) requestAnimationFrame(tick);
    })(t0);
}

function panelHTML(v) {
    const ev = v.fuel_type === "Electric";
    const reasons = (v.reasons?.length ? v.reasons : ["Matches your requirements"]).slice(0, 5);
    return `
        <div class="car-price"><span class="car-price-value">${price(v.price)}</span><span class="car-price-label">estimated price · ${esc(v.year)}</span></div>
        <div class="car-specs">
            ${ev ? spec("Range", num(v.range_km) === null ? "N/A" : `${v.range_km} km`) : spec("Mileage", num(v.mileage) === null ? "N/A" : `${v.mileage} km/l`)}
            ${spec("Engine", (ev ? "Electric" : num(v.engine_cc) === null ? "N/A" : `${num(v.engine_cc).toLocaleString("en-IN")} cc`) + (num(v.power_hp) ? ` · ${v.power_hp} hp` : ""))}
            ${spec("Fuel", v.fuel_type ?? "N/A")}
            ${spec("Gearbox", v.transmission ?? "N/A")}
            ${spec("Seats", v.seating_capacity ?? "N/A")}
            ${spec("Service / yr", price(v.service_cost))}
        </div>
        <div class="own-slot">${ownHTML(v)}</div>
        <div class="bars" aria-label="How well this variant fits your request">
            ${(v.breakdown || []).map(b => `<div class="bar"><span class="bar-label">${esc(b.label)}</span>
                <span class="bar-track"><i style="--w:${b.fit ?? 0}%"></i></span><span class="bar-val">${b.fit + "%"}</span></div>`).join("")}
        </div>
        <div class="reasons-wrapper">
            <div class="reasons-title">WHY THIS CAR</div>
            <div class="reasons">
                ${reasons.map(r => `<span class="reason">${esc(r)}</span>`).join("")}
                ${(v.caveats || []).map(r => `<span class="reason caveat">⚠ ${esc(r)}</span>`).join("")}
            </div>
        </div>`;
}

function renderCar(car, i) {
    const name = `${car.brand} ${car.model}`;
    const variants = car.variants?.length ? car.variants : [car];
    const card = document.createElement("article");
    card.className = "car-card";
    card.style.setProperty("--d", `${i * 90}ms`);
    card.innerHTML = `
        <div class="car-image-container"><img class="car-image" alt="${esc(name)}" loading="lazy"><span class="img-credit"></span>
            <span class="rank-badge">${i === 0 ? "★ BEST MATCH" : "#" + (i + 1)}</span>
            <a class="view-link" target="_blank" rel="noopener noreferrer">View details ↗</a></div>
        <div class="car-top">
            <div class="car-heading">
                <div class="rank">MATCH #${String(i + 1).padStart(2, "0")}</div>
                <h3 class="car-name">${esc(name)}</h3>
                <div class="car-brand">${esc(car.body_type && car.body_type !== "Other" ? car.body_type : "Car")}<span>•</span>${variants.length} variant${variants.length > 1 ? "s" : ""} matched</div>
            </div>
            <div class="ring"><svg viewBox="0 0 44 44" aria-hidden="true"><circle class="ring-bg" cx="22" cy="22" r="18"/><circle class="ring-fg" cx="22" cy="22" r="18" stroke-dasharray="${RING}" stroke-dashoffset="${RING}"/></svg><span class="ring-num">0%</span></div>
        </div>
        ${variants.length > 1 ? `<div class="variant-tabs" role="group" aria-label="Variants of ${esc(name)}">${variants.map((v, k) =>
            `<button type="button" class="variant-tab${k ? "" : " active"}" data-k="${k}" aria-pressed="${k === 0}">${esc(v.fuel_type)} · ${esc(v.transmission)}</button>`).join("")}</div>` : ""}
        <div class="variant-panel"></div>
        <div class="car-links" aria-label="More about ${esc(name)}">
            <a class="link-details" target="_blank" rel="noopener noreferrer">Details ↗</a>
            <a class="link-photos" target="_blank" rel="noopener noreferrer">Photos ↗</a>
            <a class="link-reviews" target="_blank" rel="noopener noreferrer">Video reviews ↗</a>
            <button type="button" class="cmp-btn" aria-pressed="false">＋ Compare</button>
        </div>`;

    const panel = card.querySelector(".variant-panel");
    let curK = 0;
    card._own = () => { const slot = panel.querySelector(".own-slot"); if (slot) slot.innerHTML = ownHTML(variants[curK]); };
    const cmpBtn = card.querySelector(".cmp-btn");
    card._sync = () => {                 // the compare button always refers to the variant currently shown
        const on = cmpHas(cmpId(car, variants[curK]));
        cmpBtn.classList.toggle("on", on); cmpBtn.setAttribute("aria-pressed", String(on));
        cmpBtn.textContent = on ? "✓ Added to compare" : "＋ Compare";
    };
    cmpBtn.addEventListener("click", () => toggleCmp(car, variants[curK]));
    const paint = k => {
        curK = k; card._sync();
        panel.innerHTML = panelHTML(variants[k]);
        setRing(card, variants[k].recommendation_score);
        card.querySelectorAll(".variant-tab").forEach(b => { const on = +b.dataset.k === k; b.classList.toggle("active", on); b.setAttribute("aria-pressed", String(on)); });
    };
    card.querySelectorAll(".variant-tab").forEach(b => b.addEventListener("click", () => paint(+b.dataset.k)));
    paint(0);

    const img = card.querySelector(".car-image"), credit = card.querySelector(".img-credit");
    const fallback = placeholder(car.brand, car.model);
    img.classList.add("is-placeholder");
    img.src = fallback;
    const showPhoto = (url, note, onFail, onOk) => {
        const t = new Image();
        t.onload = () => { img.classList.remove("is-placeholder"); img.src = url; credit.textContent = note || ""; if (onOk) onOk(); };
        t.onerror = () => onFail && onFail();
        t.src = url;
    };
    /* click-through links: your own link > Wikipedia article > web search */
    const q = encodeURIComponent(`${name} India`);
    const manualPage = window.CAR_PAGE_LINKS && window.CAR_PAGE_LINKS[name];
    const detailsA = card.querySelector(".link-details"), viewA = card.querySelector(".view-link");
    const setDetails = (url, label) => { detailsA.href = viewA.href = url; detailsA.textContent = label + " ↗"; };
    setDetails(manualPage || `https://www.google.com/search?q=${q}`, manualPage ? "Official page" : "Details");
    card.querySelector(".link-photos").href = `https://www.google.com/search?tbm=isch&q=${q}`;
    card.querySelector(".link-reviews").href = `https://www.youtube.com/results?search_query=${encodeURIComponent(name + " review")}`;

    let localOk = false;
    const lookup = () => findCarImage(car.brand, car.model).then(r => {
        if (!r) return;
        if (r.page && !manualPage) setDetails(r.page, "Wikipedia");
        if (!localOk && r.url) showPhoto(r.url, r.credit);
    });
    if (car.image_url) showPhoto(API_BASE + car.image_url, "", () => {}, () => { localOk = true; });
    lookup();
    return card;
}

function renderResults(data, extraNotes = []) {
    const p = data.understood_preferences || {};
    const sentence = data.refined ? refineSentence(data) : agentSentence(p);
    agent.innerHTML = `<div class="agent-avatar" aria-hidden="true">A</div><div class="agent-msg"><p>${esc(sentence)}${data.ai ? ' <span class="ai-tag">✨ read with AI</span>' : ""}</p>
        ${data.stats ? `<span class="agent-stats">Searched ${data.stats.listings.toLocaleString("en-IN")} listings · ${data.stats.matched.toLocaleString("en-IN")} matched across ${data.stats.models} models</span>` : ""}
        ${trail.length > 1 ? `<span class="agent-trail" title="Your conversation so far">${trail.map(esc).join(" → ")}</span>` : ""}</div>`;
    renderPreferences(data.summary);
    const note = [data.notice, ...extraNotes].filter(Boolean).join(" ");
    el.notice.textContent = note;
    el.notice.classList.toggle("hidden", !note);
    el.cars.replaceChildren(...data.recommendations.map(renderCar));
    const cards = el.cars.children;              // first card is featured; avoid a lonely half-width last card
    cards[0].classList.add("wide");
    if (cards.length > 1 && (cards.length - 1) % 2 === 1) cards[cards.length - 1].classList.add("wide");

    followBox.innerHTML = `<div class="followups-title">Refine these results — I'll remember what you've asked so far:</div>` + followUps(p).map(([label, opts]) =>
        `<div class="fu-group"><span class="fu-label">${esc(label)}</span>${opts.map(([t, add]) =>
            `<button type="button" class="fu-chip" data-add="${esc(add)}">${esc(t)}</button>`).join("")}</div>`).join("") +
        `<form class="refine-form" autocomplete="off"><input class="refine-input" maxlength="120" aria-label="Refine these results"
            placeholder="Type a change, e.g. only automatic · no diesel · under 12 lakh · add Hyundai">
            <button type="submit" class="refine-btn">Refine</button><button type="button" class="refine-reset">Start over</button></form>`;
    followBox.querySelectorAll(".fu-chip").forEach(b => b.addEventListener("click", () => searchCars(b.dataset.add, { refine: true })));
    const rf = followBox.querySelector(".refine-form"), ri = followBox.querySelector(".refine-input");
    rf.addEventListener("submit", e => { e.preventDefault(); if (ri.value.trim()) searchCars(ri.value, { refine: true }); else ri.focus(); });
    followBox.querySelector(".refine-reset").addEventListener("click", () => { lastPrefs = null; trail = []; clearCompare(); backToSearch(); });
    syncCmpButtons();
    show("results");
}

/* ---------- searching ---------- */
/* Ask the server; if it is unreachable/broken, fall back to the copy of the engine that runs in the browser. */
async function getData(q, signal, prev, ref) {
    try {
        const res = await fetch(API_BASE + "/recommend", {
            method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify(prev ? { query: q, previous: prev, reference_price: ref } : { query: q }), signal,
        });
        let data = null;
        try { data = await res.json(); } catch { /* handled below */ }
        if (res.status === 422) {
            const e = new Error("Please describe the car you are looking for (up to 300 characters)."); e.fatal = true; throw e;
        }
        if (!res.ok || !data || !Array.isArray(data.recommendations)) throw new Error("The server had a problem.");
        return data;
    } catch (err) {
        if (err.fatal || (signal.aborted && signal.reason !== "timeout" && err.name === "AbortError")) throw err;
        if (typeof window.localRecommend === "function") {
            const ai = window.aiUnderstand && !prev ? await window.aiUnderstand(q, signal).catch(() => null) : null;
            const data = prev ? window.localRecommend(q, null, prev, ref) : window.localRecommend(q, ai);
            data.offline = true;
            return data;
        }
        throw err;
    }
}

async function searchCars(query, opts = {}) {
    const q = query.trim().replace(/\s+/g, " ");
    if (!q) {
        setHint("Tell us what you're looking for — e.g. “7 seater automatic under 25 lakh”.");
        el.input.focus();
        return;
    }
    setHint("");
    const follow = Boolean(opts.refine && lastPrefs);      // a follow-up refines the last search instead of starting a new one
    lastJob = { q, refine: follow };
    if (!follow) {
        lastQuery = q; trail = [q]; clearCompare();
        el.input.value = q;
        try { history.replaceState(null, "", "?q=" + encodeURIComponent(q)); } catch {}
    }

    controller?.abort();
    clearTimeout(slowTimer);
    controller = new AbortController();
    const myId = ++requestId;
    const timeout = setTimeout(() => controller.abort("timeout"), REQUEST_TIMEOUT_MS);

    el.loadingText.textContent = follow ? "Refining your search…" : window.aiUnderstand ? "Claude is reading your request…" : "AutoMind is analyzing your requirements.";
    slowTimer = setTimeout(() => {
        el.loadingText.textContent = "Still working — the server may be waking up. This can take up to a minute.";
    }, 6000);
    show("loading");
    goToResults();

    try {
        const data = await getData(q, controller.signal, follow ? lastPrefs : null, follow ? lastRef : null);
        if (myId !== requestId) return;                       // a newer search superseded this one
        if (!data || !Array.isArray(data.recommendations)) throw new Error("The server returned an unexpected response.");
        if (!data.recommendations.length) { show("empty"); return; }

        if (follow) trail.push(q);
        lastPrefs = data.understood_preferences || null;
        lastRef = data.recommendations[0]?.price ?? null;
        renderResults(data, follow ? [] : opts.notes || []);
        goToResults();
        el.title.focus({ preventScroll: true });
    } catch (err) {
        if (myId !== requestId) return;
        console.error("Recommendation error:", err);
        const local = ["localhost", "127.0.0.1"].includes(location.hostname) || location.protocol === "file:";
        showError(
            err.name === "AbortError" || controller.signal.reason === "timeout"
                ? "The server took too long to respond. Please try again."
                : err instanceof TypeError
                    ? "We couldn't reach the server. Check your connection and try again."
                        + (local ? " (Developer tip: start the backend with “uvicorn main:app --reload”.)" : "")
                    : err.message
        );
    } finally {
        clearTimeout(timeout);
        if (myId === requestId) clearTimeout(slowTimer);
    }
}


/* ---------- compare up to 3 cars side by side ---------- */
const MAX_CMP = 3;
let cmp = [];                                                   // snapshots: they survive refining the search
const cmpId = (c, v) => [c.brand, c.model, v.fuel_type, v.transmission].join("|");
const cmpHas = id => cmp.some(x => x.id === id);
const tray = Object.assign(document.createElement("div"), { id: "cmpTray", className: "cmp-tray hidden" });
const modal = Object.assign(document.createElement("div"), { id: "cmpModal", className: "cmp-modal hidden" });
modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true"); modal.setAttribute("aria-labelledby", "cmpTitle");
document.body.append(tray, modal);
let cmpNote = "", cmpNoteTimer = null;

const syncCmpButtons = () => [...el.cars.children].forEach(c => c._sync && c._sync());
function toggleCmp(car, v) {
    const id = cmpId(car, v);
    if (cmpHas(id)) cmp = cmp.filter(x => x.id !== id);
    else if (cmp.length >= MAX_CMP) { notifyCmp(`You can compare up to ${MAX_CMP} cars - remove one first.`); return; }
    else cmp.push({ id, brand: car.brand, model: car.model, body_type: car.body_type, segment: car.segment, v });
    renderTray(); syncCmpButtons();
}
function notifyCmp(msg) {
    cmpNote = msg; renderTray(); clearTimeout(cmpNoteTimer);
    cmpNoteTimer = setTimeout(() => { cmpNote = ""; renderTray(); }, 3000);
}
function clearCompare() { cmp = []; cmpNote = ""; renderTray(); closeCompare(); syncCmpButtons(); }
function renderTray() {
    tray.classList.toggle("hidden", !cmp.length);
    tray.innerHTML = `<div class="cmp-items">${cmp.map(x => `<span class="cmp-chip">${esc(x.brand + " " + x.model)} <small>${esc(x.v.fuel_type)}</small>
            <button type="button" data-rm="${esc(x.id)}" aria-label="Remove ${esc(x.model)} from comparison">×</button></span>`).join("")}</div>
        <div class="cmp-actions">${cmpNote ? `<span class="cmp-note" role="status">${esc(cmpNote)}</span>` : `<span class="cmp-count">${cmp.length}/${MAX_CMP}</span>`}
        <button type="button" class="cmp-go" ${cmp.length < 2 ? "disabled" : ""}>${cmp.length < 2 ? "Pick one more to compare" : "Compare now"}</button>
        <button type="button" class="cmp-clear">Clear</button></div>`;
    tray.querySelectorAll("[data-rm]").forEach(b => b.addEventListener("click", () => { cmp = cmp.filter(x => x.id !== b.dataset.rm); renderTray(); syncCmpButtons(); if (cmp.length < 2) closeCompare(); else if (!modal.classList.contains("hidden")) openCompare(); }));
    tray.querySelector(".cmp-go").addEventListener("click", openCompare);
    tray.querySelector(".cmp-clear").addEventListener("click", clearCompare);
}

const ownVal = (x, f) => { const o = ownOf(x.v); return o ? f(o) : "—"; };
const ownKey = (x, k) => { const o = ownOf(x.v); return o ? o[k] : NaN; };
const CMP_ROWS = [
    { label: "Price", val: x => price(x.v.price), key: x => x.v.price, best: "min", win: "Lowest price" },
    { label: "Fuel", val: x => x.v.fuel_type },
    { label: "Gearbox", val: x => x.v.transmission },
    { label: "Mileage / range", val: x => x.v.fuel_type === "Electric" ? `${x.v.range_km} km range` : `${x.v.mileage} km/l` },
    { label: "Running cost per km", val: x => `₹${(+x.v.cost_per_km).toFixed(1)}`, key: x => x.v.cost_per_km, best: "min", win: "Cheapest to run" },
    { label: "Engine", val: x => x.v.engine_cc ? `${Number(x.v.engine_cc).toLocaleString("en-IN")} cc` : "Electric motor" },
    { label: "Power", val: x => `${x.v.power_hp} bhp`, key: x => x.v.power_hp, best: "max", win: "Most powerful" },
    { label: "Seats", val: x => x.v.seating_capacity, key: x => x.v.seating_capacity, best: "max", win: "Most seats" },
    { label: "Service cost / year (est.)", val: x => price(x.v.service_cost), key: x => x.v.service_cost, best: "min", win: "Lowest service cost" },
    { label: "Monthly EMI", val: x => ownVal(x, o => o.hasLoan ? rupees(o.emi) : "No loan"), key: x => ownKey(x, "emi"), best: "min", win: "Lowest EMI" },
    { label: "Fuel / electricity per month", val: x => ownVal(x, o => rupees(o.fuelMonthly)), key: x => ownKey(x, "fuelMonthly"), best: "min", win: "Cheapest to fuel" },
    { label: "Total 5-year cost", val: x => ownVal(x, o => price(o.total)), key: x => ownKey(x, "total"), best: "min", win: "Lowest 5-year cost" },
    { label: "Model year", val: x => x.v.year, key: x => x.v.year, best: "max", win: "Newest" },
    { label: "Body type", val: x => x.body_type },
    { label: "Match for your search", val: x => `${x.v.recommendation_score}%`, key: x => x.v.recommendation_score, best: "max", win: "Best match" },
];
function openCompare() {
    if (cmp.length < 2) return;
    const wins = [];
    const rows = CMP_ROWS.map(r => {
        let bestIdx = new Set();
        if (r.key && cmp.every(x => Number.isFinite(Number(r.key(x))))) {
            const ks = cmp.map(r.key), top = r.best === "min" ? Math.min(...ks) : Math.max(...ks);
            if (ks.some(k => k !== top)) {                       // only highlight when the cars actually differ
                ks.forEach((k, i) => { if (k === top) bestIdx.add(i); });
                if (bestIdx.size === 1) wins.push(`${r.win}: ${cmp[[...bestIdx][0]].brand} ${cmp[[...bestIdx][0]].model}`);
            }
        }
        return `<tr><th scope="row">${esc(r.label)}</th>${cmp.map((x, i) => `<td class="${bestIdx.has(i) ? "best" : ""}">${esc(r.val(x))}${bestIdx.has(i) ? ' <span class="tick" aria-label="best">✓</span>' : ""}</td>`).join("")}</tr>`;
    }).join("");
    modal.innerHTML = `<div class="cmp-backdrop" data-close></div>
        <div class="cmp-panel"><div class="cmp-head"><h3 id="cmpTitle">Compare cars</h3><button type="button" class="cmp-close" data-close aria-label="Close comparison">×</button></div>
        <div class="cmp-scroll"><table class="cmp-table"><thead><tr><th></th>${cmp.map(x => `<th scope="col"><span class="cmp-name">${esc(x.brand + " " + x.model)}</span>
            <small>${esc(x.v.fuel_type)} · ${esc(x.v.transmission)}</small></th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
        ${wins.length ? `<div class="cmp-verdict"><b>At a glance</b>${wins.map(w => `<span>${esc(w)}</span>`).join("")}</div>` : ""}
        <p class="cmp-foot">✓ marks the best value in each row. Prices and specs are estimates from a sample dataset. Ownership rows use your daily distance and down payment.</p></div>`;
    modal.classList.remove("hidden"); document.body.classList.add("cmp-open");
    modal.querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", closeCompare));
    modal.querySelector(".cmp-close").focus();
}
function closeCompare() {
    if (modal.classList.contains("hidden")) return;
    modal.classList.add("hidden"); document.body.classList.remove("cmp-open");
    tray.querySelector(".cmp-go")?.focus();
}
document.addEventListener("keydown", e => { if (e.key === "Escape") closeCompare(); });

/* ---------- events ---------- */

/* ---------- guided 10-question car finder ---------- */
const quizQuestions = [
    { key:"budget", question:"What is your budget?", options:[
        ["Under ₹8 lakh","up to 8 lakh"],["₹8–12 lakh","8 to 12 lakh"],["₹12–20 lakh","12 to 20 lakh"],["₹20–30 lakh","20 to 30 lakh"],["₹30–50 lakh","30 to 50 lakh"],["₹50 lakh+","over 50 lakh"]
    ]},
    { key:"use", question:"What will you mainly use the car for?", options:[
        ["City driving","city driving"],["Highway & long trips","highway"],["Family use","family"],["Off-road & adventure","off road"],["Business / client use","impress clients"],["Mixed usage","mixed"]
    ]},
    { key:"seats", question:"How many people should it comfortably seat?", options:[
        ["1–2 people","any seats"],["3–4 people","4 seater"],["5 people","5 seater"],["6 or more people","7 seater"]
    ]},
    { key:"fuel", question:"Which fuel or powertrain do you prefer?", options:[
        ["Petrol","petrol"],["Diesel","diesel"],["CNG","cng"],["Hybrid","hybrid"],["Electric","electric"],["No preference","no fuel preference"]
    ]},
    { key:"body", question:"What type of car do you want?", options:[
        ["Hatchback","hatchback"],["Sedan","sedan"],["SUV","suv"],["MUV / MPV","mpv"],["Coupe","coupe"],["No preference","no body preference"]
    ]},
    { key:"transmission", question:"Which transmission do you prefer?", options:[
        ["Manual","manual"],["Automatic","automatic"],["Either","either"]
    ]},
    { key:"priority", question:"What matters most to you?", options:[
        ["Mileage / running cost","mileage priority"],["Performance","performance priority"],["Comfort & space","spacious"],["Safety","safety"],["Features & technology","features"],["Looks / style","stylish"],["Low maintenance","low maintenance"]
    ]},
    { key:"performance", question:"How important is performance to you?", options:[
        ["Not important","not important"],["Moderate","moderate"],["Important","important"],["Very important","very important"]
    ]},
    { key:"feature", question:"Which feature matters most to you?", options:[
        ["ADAS / advanced safety","ADAS"],["360° camera","360 camera"],["Sunroof","sunroof"],["Premium audio","premium audio"],["Ventilated seats","ventilated seats"],["Connected-car tech","connected car tech"],["No specific feature","no specific feature"]
    ]},
    { key:"ownership", question:"What kind of ownership experience do you want?", options:[
        ["Cheapest to maintain","low maintenance"],["Balanced","balanced"],["Premium / luxury","premium"],["Sporty / fun","performance"],["Maximum comfort","spacious"]
    ]}
];

const quizState = { index:0, answers:{} };
const qel = {
    overlay: $("quizOverlay"), start: $("guidedStart"), close: $("quizClose"),
    bar: $("quizProgressBar"), progress: $("quizProgressText"), title: $("quizTitle"),
    question: $("quizQuestion"), options: $("quizOptions"), back: $("quizBack"), next: $("quizNext")
};

function openQuiz(){
    quizState.index=0; quizState.answers={}; renderQuiz();
    qel.overlay.classList.remove("hidden"); qel.overlay.setAttribute("aria-hidden","false");
    document.body.classList.add("quiz-open");
    qel.title.focus({ preventScroll:true });
}
function closeQuiz(){
    qel.overlay.classList.add("hidden"); qel.overlay.setAttribute("aria-hidden","true");
    document.body.classList.remove("quiz-open"); qel.start?.focus();
}
function renderQuiz(){
    const q=quizQuestions[quizState.index], chosen=quizState.answers[q.key];
    qel.progress.textContent=`${quizState.index+1} of ${quizQuestions.length}`;
    qel.bar.style.width=`${((quizState.index+1)/quizQuestions.length)*100}%`;
    qel.title.textContent=quizState.index===9 ? "One last choice." : "Let's find your car.";
    qel.question.textContent=q.question;
    qel.options.replaceChildren(...q.options.map(([label,value])=>{
        const b=document.createElement("button"); b.type="button"; b.className="quiz-option";
        if(chosen===value) b.classList.add("selected");
        b.innerHTML=`<span class="option-title">${esc(label)}</span>`;
        b.addEventListener("click",()=>{ quizState.answers[q.key]=value; renderQuiz(); });
        return b;
    }));
    qel.back.disabled=quizState.index===0; qel.back.style.opacity=quizState.index===0?.25:.65;
    qel.next.disabled=!chosen; qel.next.textContent=quizState.index===quizQuestions.length-1?"Find my cars →":"Next →";
}
const QUIZ_SKIP = new Set(["mixed","any seats","no fuel preference","no body preference","either","not important","moderate","no specific feature","balanced"]);
const QUIZ_UNMEASURED = { safety:"Safety ratings", features:"Feature lists", ADAS:"ADAS", "360 camera":"360° camera", sunroof:"Sunroof", "premium audio":"Premium audio", "ventilated seats":"Ventilated seats", "connected car tech":"Connected-car tech" };
function buildQuiz(){
    const a=quizState.answers, parts=[], gaps=[];
    const add=v=>{ if(v && !QUIZ_SKIP.has(v) && !parts.includes(v)) parts.push(v); };
    for(const k of ["budget","use","seats","fuel","body","transmission"]) add(a[k]);
    for(const v of [a.priority,a.feature]) if(QUIZ_UNMEASURED[v] && !gaps.includes(QUIZ_UNMEASURED[v])) gaps.push(QUIZ_UNMEASURED[v]);
    if(!QUIZ_UNMEASURED[a.priority]) add(a.priority);
    if(a.performance==="important"||a.performance==="very important") add("performance");
    add(a.ownership);
    const notes=gaps.length ? [`${gaps.join(", ")} ${gaps.length>1?"aren't":"isn't"} in our data, so ${gaps.length>1?"they":"it"} didn't change the ranking.`] : [];
    return { query: parts.join(", "), notes };
}
qel.start?.addEventListener("click",openQuiz);
qel.close?.addEventListener("click",closeQuiz);
qel.overlay?.addEventListener("click",e=>{if(e.target===qel.overlay)closeQuiz();});
qel.back?.addEventListener("click",()=>{if(quizState.index>0){quizState.index--;renderQuiz();}});
qel.next?.addEventListener("click",()=>{
    if(!quizState.answers[quizQuestions[quizState.index].key]) return;
    if(quizState.index<quizQuestions.length-1){quizState.index++;renderQuiz();return;}
    const { query, notes }=buildQuiz(); closeQuiz(); searchCars(query, { notes });
});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!qel.overlay.classList.contains("hidden"))closeQuiz();});

el.form.addEventListener("submit", e => { e.preventDefault(); searchCars(el.input.value); });
el.input.addEventListener("input", () => setHint(""));

document.querySelectorAll(".chip").forEach(chip =>
    chip.addEventListener("click", () => searchCars(chip.textContent)));

const backToSearch = () => {
    window.scrollTo({ top: 0, behavior: reduceMotion ? "auto" : "smooth" });
    setTimeout(() => { el.input.focus(); el.input.select(); }, reduceMotion ? 0 : 450);
};
el.again.addEventListener("click", backToSearch);
el.startOver.addEventListener("click", backToSearch);
el.retry.addEventListener("click", () => lastJob ? searchCars(lastJob.q, { refine: lastJob.refine }) : backToSearch());

/* mobile menu */
const setMenu = open => {
    el.nav.classList.toggle("active", open);
    el.menu.setAttribute("aria-expanded", String(open));
    el.menu.setAttribute("aria-label", open ? "Close menu" : "Open menu");
};
el.menu.addEventListener("click", () => setMenu(!el.nav.classList.contains("active")));
el.nav.querySelectorAll("a").forEach(a => a.addEventListener("click", () => setMenu(false)));
document.addEventListener("keydown", e => { if (e.key === "Escape") setMenu(false); });
document.addEventListener("click", e => { if (!e.target.closest(".nav-inner")) setMenu(false); });
matchMedia("(min-width: 801px)").addEventListener("change", () => setMenu(false));

/* founder page: #founder swaps the home sections for the founder profile */
const founderEl = $("founder"), founderLink = el.nav.querySelector('a[href="#founder"]'), SITE_TITLE = document.title;
function route() {
    const founder = location.hash === "#founder";
    document.body.classList.toggle("view-founder", founder);
    founderEl.classList.toggle("hidden", !founder);
    founderLink.classList.toggle("active-page", founder);
    founderLink.toggleAttribute("aria-current", founder);
    document.title = founder ? "Pranav Ranjan — Founder & Builder | AutoMind AI" : SITE_TITLE;
    if (founder) { window.scrollTo({ top: 0, behavior: "instant" }); $("founderName").focus({ preventScroll: true }); return; }
    let id = location.hash.slice(1);
    try { id = decodeURIComponent(id); } catch { /* keep the raw fragment */ }
    const target = id ? document.getElementById(id) : null;
    if (target) target.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
}
window.addEventListener("hashchange", route);
route();

/* shareable links: ?q=... runs the search on load */
const initial = new URLSearchParams(location.search).get("q");
if (initial) searchCars(initial);
