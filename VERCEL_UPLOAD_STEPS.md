# AutoMind AI — Vercel upload

## Repository root
The GitHub repository root must contain `main.py`, `requirements.txt`, `pyproject.toml`, `.python-version`, `frontend/`, `data/`, `car_images/`, `recommender.py`, `nlu.py`, and `llm.py`.

Do NOT create another `AI-Car-Recommendation/` folder inside the GitHub repository.

## Vercel settings
Import the GitHub repository.
- Framework Preset: Other (or let Vercel detect FastAPI)
- Root Directory: `.`
- Build Command: leave empty
- Output Directory: leave empty
- Install Command: leave default

Vercel's current FastAPI support is zero-configuration. `main.py` exports `app = FastAPI(...)`, which is a supported entrypoint.

## Test after deployment
Open:
1. `/`
2. `/api/health`

`/api/health` should return JSON with `"status": "ok"`.

The website uses `/api/recommend` for recommendations. The browser also has its own JavaScript recommendation engine as a fallback.

## Claude (optional)
The app does not require Claude to run. If desired, add `ANTHROPIC_API_KEY` in Vercel Project Settings → Environment Variables and redeploy.

## Important
Do not add an `api/index.py` wrapper for this version. Vercel's current FastAPI deployment supports `main.py` directly.
