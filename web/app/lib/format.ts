// Shared formatting for numbers/rates that were previously reimplemented
// independently across HeadlineCard, CategoryBreakdown, FuelPanel, and
// PersonalizeDashboard — each with its own "—" fallback and rate-color
// ternary. Kept intentionally small: components with genuinely different
// conventions (e.g. StoreComparison's >=100 baseline coloring, or a
// slider's "0.0" fallback) are left as-is rather than forced in here.

export const EMPTY = "—";

export function formatNumber(value: number | null | undefined, decimals = 2): string {
  return value != null ? value.toFixed(decimals) : EMPTY;
}

export function formatPercent(value: number | null | undefined, decimals = 2): string {
  return value != null ? `${value.toFixed(decimals)}%` : EMPTY;
}

export function formatSigned(value: number | null | undefined, decimals = 2): string {
  if (value == null) return EMPTY;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(decimals)}`;
}

export function formatSignedPercent(value: number | null | undefined, decimals = 2): string {
  return value != null ? `${formatSigned(value, decimals)}%` : EMPTY;
}

// text-red-400 (up) / text-green-400 (down) / neutral (flat) / unknown
// (null) — the project's consistent "red = up, green = down" convention for
// inflation rates and deltas. `neutral`/`unknown` are overridable since
// different components use different placeholder shades.
export function rateColorClass(
  value: number | null | undefined,
  options: { neutral?: string; unknown?: string } = {}
): string {
  const neutral = options.neutral ?? "text-neutral-300";
  const unknown = options.unknown ?? "text-neutral-400";
  if (value == null) return unknown;
  if (value > 0) return "text-red-400";
  if (value < 0) return "text-green-400";
  return neutral;
}
