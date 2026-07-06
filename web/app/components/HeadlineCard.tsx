"use client";

import type { LatestOverallResponse } from "../lib/types";

interface Props {
  latest: LatestOverallResponse;
  basis: "headline" | "effective";
  onBasisChange: (basis: "headline" | "effective") => void;
}

function formatRate(rate: number | null): string {
  if (rate === null) return "—";
  const sign = rate > 0 ? "+" : "";
  return `${sign}${rate.toFixed(2)}%`;
}

export default function HeadlineCard({ latest, basis, onBasisChange }: Props) {
  const daily = latest.fixed_basket[basis]?.daily;
  const weekly = latest.fixed_basket[basis]?.weekly;
  const monthly = latest.fixed_basket[basis]?.monthly;
  const yearly = latest.fixed_basket[basis]?.yearly;

  const headlineValue = daily?.index_value_ma7 ?? daily?.index_value ?? null;

  return (
    <section className="rounded-lg border border-neutral-800 p-6">
      <div className="mb-4 flex items-center justify-between">
        <span className="text-sm text-neutral-400">
          Fixed-basket grocery index — {latest.as_of_date ?? "no data yet"}
        </span>
        <div className="inline-flex overflow-hidden rounded border border-neutral-700 text-sm">
          {(["headline", "effective"] as const).map((b) => (
            <button
              key={b}
              onClick={() => onBasisChange(b)}
              className={`px-3 py-1 ${
                basis === b ? "bg-neutral-100 text-neutral-900" : "bg-transparent text-neutral-300"
              }`}
            >
              {b === "headline" ? "Headline (regular price)" : "Effective (displayed price)"}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-baseline gap-3">
        <span className="text-5xl font-bold tabular-nums">
          {headlineValue !== null ? headlineValue.toFixed(2) : "—"}
        </span>
        <span className="text-neutral-400">index (base 100)</span>
      </div>
      <p className="mt-1 text-xs text-neutral-500">7-day moving average of the daily index</p>

      <dl className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-4">
        <RateStat label="Daily" rate={daily?.inflation_rate ?? null} />
        <RateStat label="Weekly" rate={weekly?.inflation_rate ?? null} />
        <RateStat label="Monthly" rate={monthly?.inflation_rate ?? null} />
        <RateStat label="Yearly" rate={yearly?.inflation_rate ?? null} />
      </dl>
    </section>
  );
}

function RateStat({ label, rate }: { label: string; rate: number | null }) {
  const color = rate === null ? "text-neutral-400" : rate > 0 ? "text-red-400" : rate < 0 ? "text-green-400" : "text-neutral-300";
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className={`text-lg font-medium tabular-nums ${color}`}>{formatRate(rate)}</dd>
    </div>
  );
}
