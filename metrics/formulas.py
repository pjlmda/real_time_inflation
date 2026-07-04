"""Pure index-number math (spec §6) — the HICP elementary-aggregate
methodology: Jevons (weighted geometric mean) for within-class elementary
aggregates, weighted arithmetic mean across classes for the overall index.
No I/O here; `metrics/compute.py` handles fetching/writing.
"""
from __future__ import annotations

import math


def jevons_class_index(relatives_and_weights: list[tuple[float, float]]) -> float:
    """Weighted geometric mean of price relatives, as an index with base
    100. Each pair is `(relative, weight)` where `relative = price_t /
    price_0` for one product. Weights are renormalized to sum to 1 inside
    this call (spec §5: renormalize within whatever's covered), so callers
    don't need to pre-normalize `within_cat_weight` values."""
    total_weight = sum(w for _, w in relatives_and_weights)
    if total_weight <= 0:
        raise ValueError("total weight must be positive")
    log_sum = sum(w * math.log(r) for r, w in relatives_and_weights)
    return math.exp(log_sum / total_weight) * 100


def weighted_overall_index(indices_and_weights: list[tuple[float, float]]) -> float:
    """Weighted arithmetic mean of class indices, weights renormalized to
    sum to 1 within whatever's covered (spec §5 — partial-HICP coverage)."""
    total_weight = sum(w for _, w in indices_and_weights)
    if total_weight <= 0:
        raise ValueError("total weight must be positive")
    return sum(idx * w for idx, w in indices_and_weights) / total_weight


def inflation_rate(current: float, base: float) -> float:
    """% change of `current` relative to `base` (e.g. index_t vs an
    index_{t-P} row found for the lookback period)."""
    if base == 0:
        raise ValueError("base must be non-zero")
    return (current / base - 1) * 100
