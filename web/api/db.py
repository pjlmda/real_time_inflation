"""Read-only Supabase access for the web API.

Self-contained on purpose: Vercel's Python function build is scoped to the
project's Root Directory (`web/`), so this can't import the repo-root
`scraper`/`metrics` packages even if it wanted to — it has its own minimal
client and query helpers.

Holds `SUPABASE_SERVICE_KEY` server-side only (a Vercel environment
variable, never shipped to the browser) — the "backend holds the service
key" pattern, avoiding any need for Row Level Security policies for a
public read-only API.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

import httpx
from dotenv import load_dotenv
from supabase import Client, ClientOptions, create_client

# `stores` has no persisted `is_active` column (only config/stores.yaml's
# `active` flag) — this allowlist is what keeps a seeded-but-inactive store
# (e.g. Portugal's `lidl`) out of /health and /stores. Keyed by country now
# that the market switcher exists (docs/france-expansion-plan.md §3.4) —
# extend this list, not the whole architecture, whenever a store's active
# status changes.
ACTIVE_STORES_BY_COUNTRY: dict[str, list[str]] = {
    "PT": ["continente", "pingo-doce", "auchan"],
    "FR": ["auchan-fr-paris", "auchan-fr-marseille", "lidl-fr"],
    "US": ["wegmans-us-medford", "wegmans-us-nyc", "wegmans-us-fairfax", "wegmans-us-chapelhill"],
}
# Mirrors scraper/run.py's CATEGORY_CRAWLERS keys (this module can't import
# that repo-root package — see the module docstring). Every store here is
# PT; France's and Wegmans' stores are basket-only, no category crawler
# exists for them yet. get_health() needs this to avoid reporting every
# France/US store as permanently "unhealthy" for a category-mode scrape
# that was never expected to run there in the first place — a real, latent
# bug this file's country-scoping would otherwise have newly exposed.
CATEGORY_CRAWL_STORES = {"continente", "pingo-doce", "auchan"}
DEFAULT_COUNTRY = "PT"
# Display metadata for the market switcher — a country only actually shows
# up there if it also has real inflation_metrics rows (get_available_countries
# filters this map down to that live-confirmed subset, so US won't appear
# until its weights sync lands and metrics/compute.py has run for it).
COUNTRY_INFO: dict[str, dict] = {
    "PT": {"name": "Portugal", "currency": "EUR"},
    "FR": {"name": "France", "currency": "EUR"},
    "US": {"name": "United States", "currency": "USD"},
}
COVERAGE_ALERT_THRESHOLD = 0.85
STALE_AFTER_HOURS = 36


@lru_cache
def get_client() -> Client:
    # No-op in production (Vercel injects env vars directly, and load_dotenv
    # never overrides an already-set variable) — only meaningful for local dev.
    load_dotenv()
    # supabase-py's default httpx client negotiates HTTP/2, and this one
    # Client instance is shared (lru_cache) across every concurrent request
    # this process serves. Each page load fires ~6-8 concurrent API calls
    # (see web/app/page.tsx's Promise.all), and Supabase's gateway disconnects
    # that shared HTTP/2 connection under a concurrent burst, surfacing as
    # httpx.RemoteProtocolError: Server disconnected — confirmed live via a
    # concurrent curl burst against /api/stores. Forcing HTTP/1.1 gives each
    # concurrent request its own pooled connection instead of multiplexing
    # over one connection that's vulnerable to being killed mid-burst.
    transport = httpx.Client(http2=False)
    return create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_KEY"],
        options=ClientOptions(httpx_client=transport),
    )


def _is_stale(iso_timestamp: str | None) -> bool:
    if not iso_timestamp:
        return True
    ts = datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - ts) > timedelta(hours=STALE_AFTER_HOURS)


class SupabaseReader:
    def __init__(self, client: Client | None = None, country: str = DEFAULT_COUNTRY):
        self.client = client or get_client()
        self.country = country

    # --- /countries ---

    def get_available_countries(self) -> list[dict]:
        # Only countries with real inflation_metrics rows are offered in the
        # switcher — US is seeded/scraped but has none yet (weights sync
        # still pending), so it stays absent here until that actually lands,
        # rather than showing a country that would render an empty dashboard.
        rows = self.client.table("inflation_metrics").select("country").execute().data
        present = {row["country"] for row in rows}
        return [
            {"code": code, "name": info["name"], "currency": info["currency"]}
            for code, info in COUNTRY_INFO.items()
            if code in present
        ]

    # --- /health ---

    def get_health(self) -> dict:
        active_slugs = ACTIVE_STORES_BY_COUNTRY.get(self.country, [])
        stores: dict[str, dict] = {}
        healthy = True

        store_rows = (
            self.client.table("stores").select("id, slug").in_("slug", active_slugs).execute().data
            if active_slugs
            else []
        )
        store_id_by_slug = {row["slug"]: row["id"] for row in store_rows}
        store_ids = list(store_id_by_slug.values())

        # One batched fetch of recent scrape_runs across every target store,
        # instead of one query per (store, mode) — up to ~11 sequential round
        # trips for a single /api/health call before this fix. Grouped below
        # by taking the first (most recent, since desc-ordered) row per
        # (store_id, mode), the same pattern get_products() already uses for
        # latest price_snapshots. The limit is a fixed constant sized well
        # above what STALE_AFTER_HOURS could ever need per store/mode — not a
        # full-history scan (scrape_runs would otherwise grow unbounded the
        # same way inflation_metrics does).
        recent_runs = (
            self.client.table("scrape_runs")
            .select("store_id, mode, status, coverage, finished_at, blocked, started_at")
            .in_("store_id", store_ids)
            .order("started_at", desc=True)
            .limit(200)
            .execute()
            .data
            if store_ids
            else []
        )
        latest_by_store_mode: dict[tuple[int, str], dict] = {}
        for run in recent_runs:
            latest_by_store_mode.setdefault((run["store_id"], run["mode"]), run)

        for slug in active_slugs:
            store_id = store_id_by_slug.get(slug)
            if store_id is None:
                continue
            modes = ("basket", "category") if slug in CATEGORY_CRAWL_STORES else ("basket",)
            per_mode: dict[str, dict | None] = {}
            for mode in modes:
                run = latest_by_store_mode.get((store_id, mode))
                row = (
                    {
                        "status": run["status"],
                        "coverage": run["coverage"],
                        "finished_at": run["finished_at"],
                        "blocked": run["blocked"],
                    }
                    if run
                    else None
                )
                per_mode[mode] = row
                if row is None or row["status"] == "failed" or (row["coverage"] or 0) < COVERAGE_ALERT_THRESHOLD:
                    healthy = False
            stores[slug] = per_mode

        compute_resp = (
            self.client.table("inflation_metrics")
            .select("computed_at")
            .eq("country", self.country)
            .order("computed_at", desc=True)
            .limit(1)
            .execute()
        )
        latest_computed_at = compute_resp.data[0]["computed_at"] if compute_resp.data else None
        compute_stale = _is_stale(latest_computed_at)

        # fuel_prices is genuinely Portugal-only (see get_fuel_latest) - no
        # staleness signal applies to any other country, not a missing filter.
        latest_fetched_at = None
        fuel_stale = False
        if self.country == "PT":
            fuel_resp = self.client.table("fuel_prices").select("fetched_at").order("fetched_at", desc=True).limit(1).execute()
            latest_fetched_at = fuel_resp.data[0]["fetched_at"] if fuel_resp.data else None
            fuel_stale = _is_stale(latest_fetched_at)

        return {
            "healthy": healthy and not compute_stale,
            "stores": stores,
            "compute": {"latest_computed_at": latest_computed_at, "stale": compute_stale},
            "fuel": {"latest_fetched_at": latest_fetched_at, "stale": fuel_stale},
        }

    # --- /inflation/latest ---

    def get_latest_as_of_date(self) -> str | None:
        resp = (
            self.client.table("inflation_metrics")
            .select("as_of_date")
            .eq("country", self.country)
            .order("as_of_date", desc=True)
            .limit(1)
            .execute()
        )
        return resp.data[0]["as_of_date"] if resp.data else None

    def get_latest_overall(self) -> dict:
        as_of_date = self.get_latest_as_of_date()
        if as_of_date is None:
            return {"as_of_date": None, "fixed_basket": {}, "category_avg": {}}

        resp = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "overall")
            .eq("country", self.country)
            .execute()
        )
        result: dict = {"as_of_date": as_of_date, "fixed_basket": {}, "category_avg": {}}
        for row in resp.data:
            family = row["index_family"]
            basis = row["price_basis"]
            result.setdefault(family, {}).setdefault(basis, {})[row["period"]] = _shape_metric_row(row)
        return result

    # --- /inflation/series ---

    def get_series(
        self, family: str, dimension: str, dimension_value: str, period: str, basis: str
    ) -> list[dict]:
        resp = (
            self.client.table("inflation_metrics")
            .select("as_of_date, index_value, index_value_ma7, inflation_rate, n_products, coverage")
            .eq("index_family", family)
            .eq("dimension", dimension)
            .eq("dimension_value", dimension_value)
            .eq("period", period)
            .eq("price_basis", basis)
            .eq("country", self.country)
            .order("as_of_date")
            .execute()
        )
        return [_shape_metric_row(row) | {"as_of_date": row["as_of_date"]} for row in resp.data]

    # --- /categories ---

    def get_categories(self) -> list[dict]:
        categories = self.client.table("categories").select("*").order("ecoicop2_code").execute().data

        # Weights are country-specific (migration 0007's category_weights),
        # while `categories` itself stays the shared, country-agnostic
        # COICOP taxonomy — see docs/france-expansion-plan.md §3.2.
        weights = (
            self.client.table("category_weights")
            .select("ecoicop2_code, hicp_weight")
            .eq("country", self.country)
            .execute()
            .data
        )
        weight_by_code = {row["ecoicop2_code"]: row["hicp_weight"] for row in weights}

        as_of_date = self.get_latest_as_of_date()
        latest = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "category")
            .eq("period", "daily")
            .eq("country", self.country)
            .execute()
            .data
            if as_of_date
            else []
        )
        by_code: dict[str, dict] = {}
        for row in latest:
            by_code.setdefault(row["dimension_value"], {})[f"{row['index_family']}_{row['price_basis']}"] = (
                _shape_metric_row(row)
            )

        # Each category's index is rebased to 100 on the first day it entered
        # the tracker (categories were added incrementally across several
        # basket-growth rounds, not all on day one) — surfaced per-category so
        # the "Index" column can be traced back to a concrete base date rather
        # than a single project-wide one.
        #
        # One small, indexed .limit(1) query per category rather than a
        # single query over the whole table: the previous version fetched
        # every historical daily row for every category just to find each
        # one's earliest date, so it grew without bound as history accrued
        # (this project is explicitly built to run for years — see
        # CLAUDE.md's "History accrues from day 1"). A base date never
        # changes once set, and category count is small and grows only on
        # rare basket-growth rounds, so N bounded queries here scale far
        # better over time than one query whose size is
        # categories x days-of-history-so-far. (Supabase's PostgREST doesn't
        # have aggregate functions enabled on this project — confirmed live —
        # so a single server-side MIN()-per-category query isn't available
        # without a schema migration.)
        base_date_by_code: dict[str, str] = {}
        for cat in categories:
            resp = (
                self.client.table("inflation_metrics")
                .select("as_of_date")
                .eq("dimension_value", cat["ecoicop2_code"])
                .eq("dimension", "category")
                .eq("index_family", "fixed_basket")
                .eq("price_basis", "headline")
                .eq("period", "daily")
                .eq("country", self.country)
                .order("as_of_date")
                .limit(1)
                .execute()
                .data
            )
            if resp:
                base_date_by_code[cat["ecoicop2_code"]] = resp[0]["as_of_date"]

        return [
            {
                "ecoicop2_code": cat["ecoicop2_code"],
                "name_pt": cat["name_pt"],
                "name_en": cat["name_en"],
                "hicp_weight": weight_by_code.get(cat["ecoicop2_code"]),
                "latest": by_code.get(cat["ecoicop2_code"], {}),
                "base_date": base_date_by_code.get(cat["ecoicop2_code"]),
            }
            for cat in categories
        ]

    # --- /inflation/series/bulk ---

    def get_category_series_bulk(self, family: str, period: str, basis: str) -> dict[str, list[dict]]:
        # One round trip for every category's series, instead of the N
        # separate /inflation/series calls a personalized-weights view would
        # otherwise need (see docs/future-roadmap.md Part 1).
        resp = (
            self.client.table("inflation_metrics")
            .select("dimension_value, as_of_date, index_value, index_value_ma7")
            .eq("dimension", "category")
            .eq("index_family", family)
            .eq("period", period)
            .eq("price_basis", basis)
            .eq("country", self.country)
            .order("as_of_date")
            .execute()
            .data
        )
        by_code: dict[str, list[dict]] = {}
        for row in resp:
            by_code.setdefault(row["dimension_value"], []).append(
                {
                    "as_of_date": row["as_of_date"],
                    "index_value": row["index_value"],
                    "index_value_ma7": row["index_value_ma7"],
                }
            )
        return by_code

    # --- /stores ---

    def get_stores(self) -> list[dict]:
        # `stores` has no is_active column (only config/stores.yaml's `active`
        # flag, not persisted) — filter to the stores actually being scraped.
        active_slugs = ACTIVE_STORES_BY_COUNTRY.get(self.country, [])
        stores = self.client.table("stores").select("*").in_("slug", active_slugs).execute().data if active_slugs else []
        as_of_date = self.get_latest_as_of_date()
        latest = (
            self.client.table("inflation_metrics")
            .select("*")
            .eq("as_of_date", as_of_date)
            .eq("dimension", "store")
            .eq("period", "daily")
            .eq("country", self.country)
            .execute()
            .data
            if as_of_date
            else []
        )
        by_slug: dict[str, dict] = {}
        for row in latest:
            by_slug.setdefault(row["dimension_value"], {})[f"{row['index_family']}_{row['price_basis']}"] = (
                _shape_metric_row(row)
            )

        # One batched fetch of recent basket scrape_runs across every store,
        # instead of one query per store — see get_health()'s identical fix
        # just above for the same reasoning (bounded constant limit, not a
        # full-history scan).
        store_ids = [store["id"] for store in stores]
        recent_runs = (
            self.client.table("scrape_runs")
            .select("store_id, status, coverage, finished_at, started_at")
            .in_("store_id", store_ids)
            .eq("mode", "basket")
            .order("started_at", desc=True)
            .limit(100)
            .execute()
            .data
            if store_ids
            else []
        )
        latest_run_by_store: dict[int, dict] = {}
        for run in recent_runs:
            latest_run_by_store.setdefault(run["store_id"], run)

        result = []
        for store in stores:
            slug = store["slug"]
            run = latest_run_by_store.get(store["id"])
            last_scrape = (
                {"status": run["status"], "coverage": run["coverage"], "finished_at": run["finished_at"]}
                if run
                else None
            )
            result.append(
                {
                    "slug": slug,
                    "name": store["name"],
                    "latest": by_slug.get(slug, {}),
                    "last_scrape": last_scrape,
                }
            )
        return result

    # --- /products ---

    def get_products(self) -> list[dict]:
        # products/product_listings have no direct country column of their
        # own — scoped here via a join through stores (two round trips:
        # store ids for this country, then listings at those stores) rather
        # than a products-table filter, since the same canonical_name+brand
        # product could in principle exist in more than one country.
        store_ids = [
            row["id"]
            for row in self.client.table("stores").select("id").eq("country", self.country).execute().data
        ]
        products = self.client.table("products").select("*, categories(ecoicop2_code, name_en)").eq("is_active", True).execute().data
        listings = (
            self.client.table("product_listings")
            .select("*, stores(slug)")
            .eq("is_active", True)
            .in_("store_id", store_ids)
            .execute()
            .data
            if store_ids
            else []
        )
        listing_ids = [listing["id"] for listing in listings]
        latest_snapshots: dict[int, dict] = {}
        if listing_ids:
            snapshots = (
                self.client.table("price_snapshots")
                .select("listing_id, scrape_date, price, regular_price, price_per_unit, unit_basis, is_promotion")
                .in_("listing_id", listing_ids)
                .order("scrape_date", desc=True)
                .execute()
                .data
            )
            for snap in snapshots:
                latest_snapshots.setdefault(snap["listing_id"], snap)

        listings_by_product: dict[int, list[dict]] = {}
        for listing in listings:
            snap = latest_snapshots.get(listing["id"])
            listings_by_product.setdefault(listing["product_id"], []).append(
                {
                    "store": listing["stores"]["slug"],
                    "url": listing["url"],
                    "latest_price": snap,
                }
            )

        return [
            {
                "canonical_name": product["canonical_name"],
                "brand": product["brand"],
                "category": product["categories"]["ecoicop2_code"] if product.get("categories") else None,
                "package_size": product["package_size"],
                "package_unit": product["package_unit"],
                "listings": listings_by_product[product["id"]],
            }
            for product in products
            # Excluded, not shown with an empty listings array, if this
            # product has no listing at any store in the selected country.
            if product["id"] in listings_by_product
        ]

    # --- /fuel/latest ---

    def get_fuel_latest(self) -> list[dict]:
        # fuel_prices has no country column at all (migration 0004, predates
        # multi-country) — it's genuinely Portugal-only (DGEG, Portugal's own
        # energy regulator), not a scoping gap to paper over. Empty result
        # for any other country is the honest answer, not a missing filter.
        if self.country != "PT":
            return []
        rows = self.client.table("fuel_prices").select("*").order("scrape_date", desc=True).execute().data
        by_fuel_type: dict[str, list[dict]] = {}
        for row in rows:
            by_fuel_type.setdefault(row["fuel_type"], []).append(row)

        result = []
        for fuel_type, history in by_fuel_type.items():
            latest = history[0]
            week_ago_date = (
                datetime.fromisoformat(latest["scrape_date"]).date() - timedelta(days=7)
            ).isoformat()
            week_ago = next((r for r in history if r["scrape_date"] <= week_ago_date), None)
            result.append(
                {
                    "fuel_type": fuel_type,
                    "scrape_date": latest["scrape_date"],
                    "price": latest["price"],
                    "unit": latest["unit"],
                    "week_ago_price": week_ago["price"] if week_ago else None,
                }
            )
        return result


def _shape_metric_row(row: dict) -> dict:
    coverage = row.get("coverage")
    return {
        "index_value": row.get("index_value"),
        "index_value_ma7": row.get("index_value_ma7"),
        "inflation_rate": row.get("inflation_rate"),
        "n_products": row.get("n_products"),
        "coverage": coverage,
        "low_confidence": (coverage is not None and coverage < COVERAGE_ALERT_THRESHOLD),
    }
