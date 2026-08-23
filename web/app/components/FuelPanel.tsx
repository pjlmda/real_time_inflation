import { memo } from "react";
import type { FuelRow } from "../lib/types";
import { formatSigned, rateColorClass } from "../lib/format";

const LABELS: Record<FuelRow["fuel_type"], string> = {
  gasoline_95: "Gasoline 95",
  diesel: "Diesel",
  lpg_auto: "LPG (auto)",
  gasoline_regular: "Regular gasoline",
};

// One-line provenance caption per country, mirroring the small per-country
// map shape already used elsewhere (ACTIVE_STORES_BY_COUNTRY, COUNTRY_INFO
// in web/api/db.py) rather than widening FuelRow with a per-row source field.
const CAPTIONS: Record<string, string> = {
  PT: "DGEG national daily average — a first prototype, not yet split by brand.",
  US: "EIA weekly national average (regular gasoline & diesel only) — not yet split by brand or region.",
};

function FuelPanel({ fuel, country }: { fuel: FuelRow[]; country: string }) {
  if (fuel.length === 0) return null;
  const caption = Object.hasOwn(CAPTIONS, country)
    ? CAPTIONS[country]
    : "National average — not yet split by brand.";

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5 sm:p-6">
      <h2 className="text-base font-medium text-ink">Fuel prices</h2>
      <p className="mt-1 text-sm text-ink2">{caption}</p>
      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {fuel.map((f) => {
          const delta = f.week_ago_price != null ? f.price - f.week_ago_price : null;
          return (
            <div key={f.fuel_type} className="rounded-lg border border-hairline bg-surface2 p-3.5">
              <div className="text-xs text-ink3">{LABELS[f.fuel_type]}</div>
              <div className="text-2xl font-semibold tabular-nums text-ink">
                {f.price.toFixed(3)} <span className="text-sm font-normal text-ink2">{f.unit}</span>
              </div>
              <div className="text-xs text-ink3">
                {delta === null ? (
                  "no week-ago comparison yet"
                ) : (
                  <span className={rateColorClass(delta, { neutral: "text-ink3" })}>
                    {formatSigned(delta, 3)} vs. a week ago
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default memo(FuelPanel);
