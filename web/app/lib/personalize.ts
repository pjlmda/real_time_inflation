// Client-side personalized-weights math (docs/future-roadmap.md Part 1).
// Deliberately no backend involvement: a personalized index is the exact
// same weighted-arithmetic-mean formula already implemented and tested in
// metrics/formulas.py:weighted_overall_index, just re-run in the browser
// with user-chosen weights instead of hicp_weight. No new table, no auth —
// the weight vector lives entirely in the URL so a personalized view is
// shareable as a plain link.

export interface WeightableCategory {
  ecoicop2_code: string;
  hicp_weight: number | null;
}

export function defaultWeights(categories: WeightableCategory[]): Record<string, number> {
  const weights: Record<string, number> = {};
  for (const cat of categories) {
    weights[cat.ecoicop2_code] = cat.hicp_weight ?? 0;
  }
  return weights;
}

export function encodeWeights(weights: Record<string, number>): string {
  return Object.entries(weights)
    .map(([code, w]) => `${code}:${Number(w.toFixed(4))}`)
    .join(",");
}

// Any code missing from `param`, or with an unparseable/negative value,
// falls back to that category's official HICP weight — a malformed or
// partial link degrades to "mostly official" rather than breaking.
export function decodeWeights(param: string | null, categories: WeightableCategory[]): Record<string, number> {
  const weights = defaultWeights(categories);
  if (!param) return weights;
  for (const pair of param.split(",")) {
    const [code, raw] = pair.split(":");
    if (!code || raw === undefined || !(code in weights)) continue;
    const value = Number(raw);
    if (!Number.isFinite(value) || value < 0) continue;
    weights[code] = value;
  }
  return weights;
}

// Raw slider values are relative weights, not percentages — like the
// official hicp_weight column, they don't need to (and shouldn't have to)
// sum to 100 for the math to be correct, since weightedOverallIndex already
// renormalizes by the total. This turns them into the percentages a user
// actually expects to see, for display only (negative values floor to 0).
export function normalizedShares(weights: Record<string, number>): Record<string, number> {
  const total = Object.values(weights).reduce((sum, w) => sum + Math.max(w, 0), 0);
  const shares: Record<string, number> = {};
  for (const [code, w] of Object.entries(weights)) {
    shares[code] = total > 0 ? (Math.max(w, 0) / total) * 100 : 0;
  }
  return shares;
}

// Mirrors metrics/formulas.py:weighted_overall_index — weighted arithmetic
// mean, renormalized within whatever's covered. Categories with a null
// index on a given day are excluded from that day's average entirely
// (not treated as zero), the same "renormalize within the covered subset"
// rule the official index already uses for partial-HICP coverage.
export function weightedOverallIndex(indicesAndWeights: [index: number, weight: number][]): number | null {
  const totalWeight = indicesAndWeights.reduce((sum, [, w]) => sum + w, 0);
  if (totalWeight <= 0) return null;
  const weightedSum = indicesAndWeights.reduce((sum, [idx, w]) => sum + idx * w, 0);
  return weightedSum / totalWeight;
}
