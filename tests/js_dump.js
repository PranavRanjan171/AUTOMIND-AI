// Usage: node tests/js_dump.js jobs.json -> the browser engine's answers as JSON (used by test_parity.py)
// A job is a search string, or a list of strings = a conversation where each message refines the previous result.
const fs = require("fs"), path = require("path");
global.window = {};
const root = path.join(__dirname, "..", "frontend");
(0, eval)(fs.readFileSync(path.join(root, "cars-data.js"), "utf8"));
(0, eval)(fs.readFileSync(path.join(root, "engine.js"), "utf8"));
const jobs = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const out = {};
for (const job of jobs) {
    const steps = Array.isArray(job) ? job : [job];
    let prev = null, ref = null, r = null;
    steps.forEach((q, i) => {
        r = i === 0 ? window.localRecommend(q) : window.localRecommend(q, null, prev, ref);
        prev = r.understood_preferences; ref = r.recommendations[0] && r.recommendations[0].price;
        if (steps.length > 1) out[steps.slice(0, i + 1).join(" > ")] = r;
    });
    if (steps.length === 1) out[steps[0]] = r;
}
process.stdout.write(JSON.stringify(out));
