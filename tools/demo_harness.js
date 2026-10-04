window.fetch = () => new Promise((_, rej) => setTimeout(() => rej(new TypeError("demo")), 400));
window.aiUnderstand = async (q, signal) => {
  try {
    const sample = window.claude && window.claude.use ? await window.claude.use("sample") : null;
    if (!sample) return null;
    const ctl = new AbortController(), to = setTimeout(() => ctl.abort(), 30000);
    signal.addEventListener("abort", () => ctl.abort(), { once: true });
    try { return window.sanitizeAi(await sample.json(window.AI_PROMPT + "\nRequest: " + q, { modelTier: "quick", signal: ctl.signal, cache: false })); }
    finally { clearTimeout(to); }
  } catch { return null; }
};
