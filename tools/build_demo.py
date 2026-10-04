"""Packs the website into ONE self-contained file, automind-demo.html, that works by double-click or on any static host
(no server needed - it uses the in-browser engine).      python tools/build_demo.py"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FE = ROOT / "frontend"
read = lambda p: Path(p).read_text(encoding="utf-8")

html = read(FE / "index.html")
html = html.replace('<link rel="stylesheet" href="style.css">', "<style>" + read(FE / "style.css") + "</style>")
for name in ("cars-data.js", "engine.js", "image-links.js", "ownership.js"):
    html = html.replace(f'<script src="{name}"></script>', "<script>" + read(FE / name) + "</script>")
# demo harness (no backend: skip the failing network call quickly; use Claude if the host provides it) + the app script
html = html.replace('<script src="script.js"></script>', "<script>" + read(ROOT / "tools" / "demo_harness.js") + "\n" + read(FE / "script.js") + "</script>")
assert not re.search(r'<script src="(?!http)', html), "a local script was not inlined"
(ROOT / "automind-demo.html").write_text(html, encoding="utf-8")
print(f"automind-demo.html  {len(html) / 1024:.0f} KB")
