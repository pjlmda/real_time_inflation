"""Read-only FastAPI app over `inflation_metrics` (+ supporting reads) — plan
§9, adapted to what's actually built. Deployed as a single Vercel Python
serverless function; `web/vercel.json` rewrites `/api/*` to this module.

Local dev: `uvicorn api.index:app --reload` from `web/`.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from api.db import DEFAULT_COUNTRY, SupabaseReader

app = FastAPI(title="Real-Time Grocery Inflation Tracker API")

# Same-origin under Vercel (Next.js calls this server-side) — permissive CORS
# is just a safety net for local dev, not a security boundary for this
# public, read-only API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
)

# Every endpoint below takes this same `country` param — validated against a
# plain two-letter-code pattern rather than an explicit allowlist, since the
# allowlist that actually matters (which countries have real data) lives in
# SupabaseReader.get_available_countries()/COUNTRY_INFO, not here. An
# unrecognized code just yields empty results everywhere, the same way an
# out-of-range date would — not a 400, since this is read-only public data,
# not a mutation that needs strict validation.
CountryParam = Query(DEFAULT_COUNTRY, pattern="^[A-Z]{2}$")


def get_reader(country: str) -> SupabaseReader:
    return SupabaseReader(country=country)


@app.get("/api/countries")
def countries():
    # Deliberately not itself country-scoped — this is what populates the
    # switcher in the first place.
    return get_reader(DEFAULT_COUNTRY).get_available_countries()


@app.get("/api/health")
def health(country: str = CountryParam):
    return get_reader(country).get_health()


@app.get("/api/inflation/latest")
def inflation_latest(country: str = CountryParam):
    return get_reader(country).get_latest_overall()


@app.get("/api/inflation/series")
def inflation_series(
    country: str = CountryParam,
    family: str = Query("fixed_basket", pattern="^(fixed_basket|category_avg)$"),
    dimension: str = Query("overall", pattern="^(overall|category|store)$"),
    value: str = Query("ALL"),
    period: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    basis: str = Query("headline", pattern="^(headline|effective)$"),
):
    if family == "category_avg" and basis != "effective":
        raise HTTPException(400, "category_avg only has price_basis='effective'")
    return get_reader(country).get_series(family, dimension, value, period, basis)


@app.get("/api/inflation/series/bulk")
def inflation_series_bulk(
    country: str = CountryParam,
    family: str = Query("fixed_basket", pattern="^(fixed_basket|category_avg)$"),
    period: str = Query("daily", pattern="^(daily|weekly|monthly|yearly)$"),
    basis: str = Query("headline", pattern="^(headline|effective)$"),
):
    if family == "category_avg" and basis != "effective":
        raise HTTPException(400, "category_avg only has price_basis='effective'")
    return get_reader(country).get_category_series_bulk(family, period, basis)


@app.get("/api/categories")
def categories(country: str = CountryParam):
    return get_reader(country).get_categories()


@app.get("/api/stores")
def stores(country: str = CountryParam):
    return get_reader(country).get_stores()


@app.get("/api/products")
def products(country: str = CountryParam):
    return get_reader(country).get_products()


@app.get("/api/fuel/latest")
def fuel_latest(country: str = CountryParam):
    return get_reader(country).get_fuel_latest()
