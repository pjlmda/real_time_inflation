"""Read-only FastAPI app over `inflation_metrics` (+ supporting reads) — plan
§9, adapted to what's actually built. Deployed as a single Vercel Python
serverless function; `web/vercel.json` rewrites `/api/*` to this module.

Local dev: `uvicorn api.index:app --reload` from `web/`.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.db import SupabaseReader

app = FastAPI(title="Portugal Real-Time Inflation Tracker API")

# Same-origin under Vercel (Next.js calls this server-side) — permissive CORS
# is just a safety net for local dev, not a security boundary for this
# public, read-only API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)


def get_reader() -> SupabaseReader:
    return SupabaseReader()


@app.get("/api/health")
def health():
    return get_reader().get_health()


@app.get("/api/inflation/latest")
def inflation_latest():
    return get_reader().get_latest_overall()


@app.get("/api/inflation/series")
def inflation_series(
    family: str = Query("fixed_basket", pattern="^(fixed_basket|category_avg)$"),
    dimension: str = Query("overall", pattern="^(overall|category|store)$"),
    value: str = Query("ALL"),
    period: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    basis: str = Query("headline", pattern="^(headline|effective)$"),
):
    if family == "category_avg" and basis != "effective":
        raise HTTPException(400, "category_avg only has price_basis='effective'")
    return get_reader().get_series(family, dimension, value, period, basis)


@app.get("/api/categories")
def categories():
    return get_reader().get_categories()


@app.get("/api/stores")
def stores():
    return get_reader().get_stores()


@app.get("/api/products")
def products():
    return get_reader().get_products()


@app.get("/api/fuel/latest")
def fuel_latest():
    return get_reader().get_fuel_latest()
