"""Download one verified Wikipedia photo per car model into car_images/ (run once; needs internet).

    python download_photos.py            # download missing photos
    python download_photos.py --force    # re-download everything

A photo is only accepted when the Wikipedia article title contains both the brand and the model,
so a wrong picture is never saved. Models it cannot find are listed at the end - add those by hand
(drop Brand_Model.jpg into car_images/, or add a link in frontend/image-links.js).
"""
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent
API = os.getenv("WIKI_API", "https://en.wikipedia.org/w/api.php")
HEADERS = {"User-Agent": "AutoMind-AI-student-project/1.0 (educational car recommender)"}
BRAND_ALT = {"Maruti Suzuki": ["maruti", "suzuki"], "Renault": ["renault", "dacia"], "Tata Motors": ["tata"]}
MODEL_ALT = {"Jazz": ["jazz", "fit"]}
SEARCH_BRAND = {"Tata Motors": "Tata"}
IMG_DIR = BASE / "car_images"


def norm(text):
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode().lower())


def fetch(url):
    return urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=25).read()


def find_photo(brand, model):
    params = urllib.parse.urlencode({
        "action": "query", "generator": "search", "gsrlimit": 6, "prop": "pageimages", "piprop": "thumbnail",
        "pithumbsize": 900, "format": "json", "gsrsearch": f"{SEARCH_BRAND.get(brand, brand)} {model}"})
    pages = json.loads(fetch(f"{API}?{params}")).get("query", {}).get("pages", {}).values()
    models = [norm(m) for m in MODEL_ALT.get(model, [model])]
    brands = [norm(b) for b in BRAND_ALT.get(brand, [brand])]
    for page in sorted(pages, key=lambda p: p["index"]):
        title = norm(page["title"])
        if page.get("thumbnail") and any(m in title for m in models) and any(b in title for b in brands):
            return page["thumbnail"]["source"], page["title"]
    return None, None


def main():
    force = "--force" in sys.argv
    IMG_DIR.mkdir(exist_ok=True)
    cars = pd.read_csv(BASE / "data" / "cars_india.csv")[["Brand", "Model"]].drop_duplicates()
    have = {p.stem.lower() for p in IMG_DIR.glob("*.*")}
    credits, missing, done = [], [], 0
    for brand, model in cars.itertuples(index=False):
        stem = f"{brand}_{model}".replace(" ", "_")
        if stem.lower() in have and not force:
            continue
        try:
            url, title = find_photo(brand, model)
            if not url:
                missing.append(f"{brand} {model}")
                print(f"  no verified photo: {brand} {model}")
                continue
            ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
            ext = ext if ext in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"
            (IMG_DIR / f"{stem}{ext}").write_bytes(fetch(url))
            credits.append(f"{stem}{ext} - https://en.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}")
            done += 1
            print(f"  saved {stem}{ext}")
        except Exception as exc:  # network hiccup: report and continue
            missing.append(f"{brand} {model}")
            print(f"  failed {brand} {model}: {exc}")
        time.sleep(0.4)  # be polite to Wikipedia

    if credits:
        with open(IMG_DIR / "CREDITS.txt", "a", encoding="utf-8") as f:
            f.write("\n".join(credits) + "\n")
    # let the in-browser engine know which photos exist
    js = BASE / "frontend" / "cars-data.js"
    if js.exists():
        text = js.read_text(encoding="utf-8")
        data = json.loads(text[len("window.CARS_DATA="):].rstrip().rstrip(";"))
        data["images"] = {p.stem.lower(): p.name for p in IMG_DIR.glob("*.*") if p.suffix.lower() != ".txt"}
        js.write_text("window.CARS_DATA=" + json.dumps(data, separators=(",", ":")) + ";", encoding="utf-8")
    print(f"\nDownloaded {done} photo(s). Missing: {len(missing)}")
    if missing:
        print("Add these by hand (car_images/Brand_Model.jpg or frontend/image-links.js):\n  " + "\n  ".join(missing))
    print("Photos come from Wikipedia/Wikimedia Commons; each has its own licence (mostly CC BY-SA) - see car_images/CREDITS.txt.")


if __name__ == "__main__":
    main()
