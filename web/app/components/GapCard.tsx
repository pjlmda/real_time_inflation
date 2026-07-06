import type { LatestOverallResponse } from "../lib/types";

export default function GapCard({ latest }: { latest: LatestOverallResponse }) {
  const headline = latest.fixed_basket.headline?.daily?.index_value;
  const effective = latest.fixed_basket.effective?.daily?.index_value;

  if (headline == null || effective == null) {
    return null;
  }

  const gap = effective - headline;
  const promoIntensity = gap < 0 ? Math.abs(gap) : 0;

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-medium">Headline vs. effective gap</h2>
      <p className="mt-1 text-sm text-neutral-400">
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

function Stat({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div>
      <div className="text-xs text-neutral-500">{label}</div>
      <div className={`text-xl font-medium tabular-nums ${highlight ? "text-green-400" : ""}`}>{value}</div>
    </div>
  );
}
