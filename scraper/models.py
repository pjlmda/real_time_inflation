"""Shared data shapes and exceptions for the scraper pipeline."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Listing:
    id: int
    product_id: int
    store_id: int
    url: str
    store_sku: str | None


@dataclass(frozen=True)
class ScrapedPrice:
    price: float
    regular_price: float
    price_per_unit: float
    unit_basis: str  # e.g. 'EUR/L', 'EUR/kg'
    is_promotion: bool
    promotion_label: str | None
    in_stock: bool
    raw_payload: dict


@dataclass(frozen=True)
class CategoryStats:
    n_products: int
    median: float
    mean: float
    p25: float
    p75: float


@dataclass
class RunResult:
    run_id: int
    attempted: int
    ok: int
    failed: int
    status: str  # 'success' | 'partial' | 'failed' | 'skipped' (skipped never persists to DB)
    coverage: float
    error_summary: str | None
    blocked: bool = False


class BlockDetected(Exception):
    """CAPTCHA or bot-block page detected — stop retrying immediately."""


class FetchFailed(Exception):
    """A single listing failed after exhausting retries."""


def utcnow() -> datetime:
    return datetime.utcnow()
