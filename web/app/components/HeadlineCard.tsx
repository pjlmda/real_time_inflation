"use client";

import type { LatestOverallResponse } from "../lib/types";
import { formatNumber, formatSignedPercent, rateColorClass } from "../lib/format";

interface Props {
  latest: LatestOverallResponse;
  basis: "headline" | "effective";
  onBasisChange: (basis: "headline" | "effective") => void;
}

export default function HeadlineCard({ latest, basis, onBasisChange }: Props) {
  const daily = latest.fixed_basket[basis]?.daily;
  const weekly = latest.fixed_basket[basis]?.weekly;
  const monthly = latest.fixed_basket[basis]?.monthly;
  const yearly = latest.fixed_basket[basis]?.yearly;

  const headlineValue = daily?.index_value_ma7 ?? daily?.index_value ?? null;

  return (
    <section className="rounded-xl border border-hairline border-t-2 border-t-chart1 bg-surface p-6 sm:p-7">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <span className="text-sm text-ink2">
          Fixed-basket grocery index — {latest.as_of_date ?? "no data yet"}
        </span>
        <div className="inline-flex overflow-hidden rounded-md border border-hairline text-xs sm:text-sm">
          {(["headline", "effective"] as const).map((b) => (
            <button
              key={b}
              onClick={() => onBasisChange(b)}
              className={`px-2.5 py-1 sm:px-3 transition-colors ${
                basis === b ? "bg-ink text-plane font-medium" : "bg-transparent text-ink2 hover:text-ink"
              }`}
            >
              {b === "headline" ? "Headline (regular price)" : "Effective (displayed price)"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <span className="text-6xl font-semibold text-ink">{formatNumber(headlineValue)}</span>
        <span className="text-ink2">index (base 100)</span>
      </div>
      <p className="mt-1.5 text-xs text-ink3">7-day moving average of the daily index</p>

      <dl className="mt-6 grid grid-cols-2 gap-y-4 gap-x-4 border-t border-hairline pt-5 sm:grid-cols-4">
        <RateStat label="Daily" rate={daily?.inflation_rate ?? null} />
        <RateStat label="Weekly" rate={weekly?.inflation_rate ?? null} />
        <RateStat label="Monthly" rate={monthly?.inflation_rate ?? null} />
        <RateStat label="Yearly" rate={yearly?.inflation_rate ?? null} />
      </dl>
    </section>
  );
}

function RateStat({ label, rate }: { label: string; rate: number | null }) {
  return (
    <div>
      <dt className="text-xs text-ink3">{label}</dt>
      <dd className={`text-lg font-medium tabular-nums ${rateColorClass(rate)}`}>{formatSignedPercent(rate)}</dd>
    </div>
  );
}
