import { memo } from "react";
import type { LatestOverallResponse } from "../lib/types";

function GapCard({ latest }: { latest: LatestOverallResponse }) {
  const headline = latest.fixed_basket.headline?.daily?.index_value;
  const effective = latest.fixed_basket.effective?.daily?.index_value;

  if (headline == null || effective == null) {
    return null;
  }

  const gap = effective - headline;
  const promoIntensity = gap < 0 ? Math.abs(gap) : 0;

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5 sm:p-6">
      <h2 className="text-base font-medium text-ink">Headline vs. effective gap</h2>
      <p className="mt-1 text-sm text-ink2">
        The gap between regular prices (headline) and what shoppers actually pay today
        (effective) is a signal of promo intensity.
      </p>
      <div className="mt-4 flex items-center gap-6">
        <Stat label="Headline" value={headline.toFixed(2)} />
        <Stat label="Effective" value={effective.toFixed(2)} />
        <Stat
          label="Promo intensity"
          value={`${promoIntensity.toFixed(2)} pts`}
          highlight={promoIntensity > 0}
        />
      </div>
    </section>
  );
}

export default memo(GapCard);

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-xs text-ink3">{label}</div>
      <div className={`text-xl font-medium tabular-nums ${highlight ? "text-good" : "text-ink"}`}>{value}</div>
    </div>
  );
}
