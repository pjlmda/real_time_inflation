import { memo } from "react";
import type { FuelRow } from "../lib/types";
import { formatSigned, rateColorClass } from "../lib/format";

const LABELS: Record<FuelRow["fuel_type"], string> = {
  gasoline_95: "Gasoline 95",
  diesel: "Diesel",
  lpg_auto: "LPG (auto)",
};

function FuelPanel({ fuel }: { fuel: FuelRow[] }) {
  if (fuel.length === 0) return null;

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-medium">Fuel prices</h2>
      <p className="mt-1 text-sm text-neutral-400">
        DGEG national daily average — a first prototype, not yet split by brand.
      </p>
      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {fuel.map((f) => {
          const delta = f.week_ago_price != null ? f.price - f.week_ago_price : null;
          return (
            <div key={f.fuel_type} className="rounded border border-neutral-800 p-3">
              <div className="text-xs text-neutral-500">{LABELS[f.fuel_type]}</div>
              <div className="text-2xl font-semibold tabular-nums">
                {f.price.toFixed(3)} <span className="text-sm font-normal text-neutral-400">{f.unit}</span>
              </div>
              <div className="text-xs text-neutral-500">
                {delta === null ? (
                  "no week-ago comparison yet"
                ) : (
                  <span className={rateColorClass(delta, { neutral: "" })}>
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
