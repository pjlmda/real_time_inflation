"use client";

import { useEffect, useMemo, useState } from "react";
import LineChart from "../components/LineChart";
import WeightPieChart from "../components/WeightPieChart";
import type { CategoryRow, CategorySeriesBulk, SeriesPoint } from "../lib/types";
import {
  decodeWeights,
  defaultWeights,
  encodeWeights,
  normalizedShares,
  weightedOverallIndex,
} from "../lib/personalize";

const SLIDER_MAX = 25;

export default function PersonalizeDashboard({
  categories,
  bulkSeries,
  officialSeries,
  initialWeightParam,
}: {
  categories: CategoryRow[];
  bulkSeries: CategorySeriesBulk;
  officialSeries: SeriesPoint[];
  initialWeightParam: string | null;
}) {
  const [weights, setWeights] = useState<Record<string, number>>(() =>
    decodeWeights(initialWeightParam, categories)
  );
  const [copied, setCopied] = useState(false);

  // Keep the URL in sync as sliders move, using the raw history API (not
  // Next's router) so this never triggers a server round-trip for a page
  // marked force-dynamic — this is purely address-bar bookkeeping so the
  // current view is always a shareable link, with no explicit "save" step.
  useEffect(() => {
    const url = `${window.location.pathname}?w=${encodeWeights(weights)}`;
    window.history.replaceState(null, "", url);
  }, [weights]);

  const sorted = useMemo(
    () => [...categories].sort((a, b) => (b.hicp_weight ?? 0) - (a.hicp_weight ?? 0)),
    [categories]
  );

  // Stable color per category, assigned once from sort order rather than
  // recomputed from live weights, so a slice's color never changes as its
  // slider moves — only its size does.
  const colorByCode = useMemo(() => {
    const map: Record<string, string> = {};
    sorted.forEach((cat, i) => {
      map[cat.ecoicop2_code] = `hsl(${Math.round((i * 360) / sorted.length)}, 65%, 55%)`;
    });
    return map;
  }, [sorted]);

  const totalWeight = useMemo(
    () => Object.values(weights).reduce((sum, w) => sum + Math.max(w, 0), 0),
    [weights]
  );
  const shares = useMemo(() => normalizedShares(weights), [weights]);

  // Union of every date any category has data for — categories were added
  // incrementally, so this can extend further back than any single one of
  // them (the earliest-added categories cover it) but not further than the
  // official overall series, which has existed since day one.
  const allDates = useMemo(() => {
    const set = new Set<string>();
    for (const points of Object.values(bulkSeries)) {
      for (const p of points) set.add(p.as_of_date);
    }
    return Array.from(set).sort();
  }, [bulkSeries]);

  const byCodeDate = useMemo(() => {
    const result: Record<string, Map<string, number | null>> = {};
    for (const [code, points] of Object.entries(bulkSeries)) {
      result[code] = new Map(points.map((p) => [p.as_of_date, p.index_value]));
    }
    return result;
  }, [bulkSeries]);

  // Mirrors metrics/formulas.py:weighted_overall_index, re-run per day with
  // the user's weights instead of hicp_weight. A category with no reading on
  // a given day is simply excluded from that day's average (renormalized
  // within whatever's covered), not treated as a zero.
  const personalizedValues = useMemo(
    () =>
      allDates.map((date) => {
        const pairs: [number, number][] = [];
        for (const [code, weight] of Object.entries(weights)) {
          const idx = byCodeDate[code]?.get(date);
          if (idx != null && weight > 0) pairs.push([idx, weight]);
        }
        return weightedOverallIndex(pairs);
      }),
    [allDates, byCodeDate, weights]
  );

  const officialByDate = useMemo(
    () => new Map(officialSeries.map((p) => [p.as_of_date, p.index_value])),
    [officialSeries]
  );
  const officialValues = useMemo(
    () => allDates.map((d) => officialByDate.get(d) ?? null),
    [allDates, officialByDate]
  );

  const latestPersonalized = [...personalizedValues].reverse().find((v) => v !== null) ?? null;
  const latestOfficial = officialSeries.at(-1)?.index_value ?? null;

  function resetToOfficial() {
    setWeights(defaultWeights(categories));
  }

  function copyLink() {
    navigator.clipboard.writeText(window.location.href).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-10 space-y-8">
      <header className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Personalize your inflation rate</h1>
          <p className="text-sm text-neutral-400">
            Adjust each category&apos;s weight to match your own household&apos;s spending, instead of the
            average Portuguese household HICP uses.
          </p>
        </div>
        <a
          href="/"
          className="shrink-0 rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800"
        >
          ← Back to dashboard
        </a>
      </header>

      <div className="rounded-lg border border-yellow-800 bg-yellow-950/30 p-4 text-sm text-yellow-200">
        <strong>This is a personal estimate, not an HICP-comparable figure.</strong> As soon as you change
        a weight away from the official value, the result is no longer methodologically aligned with
        INE/Eurostat HICP — it&apos;s just an application of the same formula to your own weights.
      </div>

      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 p-5">
          <div className="text-sm text-neutral-400">Your personalized index (today)</div>
          <div className="mt-1 text-3xl font-semibold tabular-nums text-emerald-400">
            {latestPersonalized != null ? latestPersonalized.toFixed(2) : "—"}
          </div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-5">
          <div className="text-sm text-neutral-400">Official HICP-comparable index (today)</div>
          <div className="mt-1 text-3xl font-semibold tabular-nums text-blue-400">
            {latestOfficial != null ? latestOfficial.toFixed(2) : "—"}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-neutral-800 p-5">
        <h2 className="text-lg font-medium">Personalized index over time</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Recomputed live from your weights below, against the same daily category indices the official
          number uses.
        </p>
        <div className="mt-4">
          <LineChart
            dates={allDates}
            series={[
              { label: "Your personalized index", color: "#34d399", values: personalizedValues },
              { label: "Official (HICP-comparable)", color: "#60a5fa", values: officialValues },
            ]}
          />
        </div>
      </section>

      <section className="rounded-lg border border-neutral-800 p-5">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-medium">Category weights</h2>
          <div className="flex gap-2 text-sm">
            <button
              onClick={resetToOfficial}
              className="rounded border border-neutral-700 px-3 py-1 text-neutral-300 hover:bg-neutral-800"
            >
              Reset to official
            </button>
            <button
              onClick={copyLink}
              className="rounded border border-neutral-700 px-3 py-1 text-neutral-300 hover:bg-neutral-800"
            >
              {copied ? "Link copied" : "Copy shareable link"}
            </button>
          </div>
        </div>
        <p className="mb-4 text-sm text-neutral-400">
          Sliders are relative weights, not percentages themselves — they&apos;re automatically
          rebalanced to add up to 100% (the <strong>Share</strong> column and the chart below), the same
          way the official HICP weights are. Raising one category&apos;s slider lowers every other
          category&apos;s share without you having to manually adjust them to compensate.
        </p>

        <div className="mb-6 flex flex-col items-center gap-4 sm:flex-row sm:items-start">
          <WeightPieChart
            slices={sorted.map((cat) => ({
              code: cat.ecoicop2_code,
              label: cat.name_en,
              value: weights[cat.ecoicop2_code] ?? 0,
              color: colorByCode[cat.ecoicop2_code],
            }))}
          />
          <div className="text-sm text-neutral-400">
            <div>
              Total raw weight: <span className="tabular-nums text-neutral-200">{totalWeight.toFixed(1)}</span>
            </div>
            <div className="mt-1">Always shown normalized to 100% — the chart and Share column reflect that, regardless of this raw total.</div>
          </div>
        </div>

        <div className="space-y-3">
          {sorted.map((cat) => {
            const weight = weights[cat.ecoicop2_code] ?? 0;
            const share = shares[cat.ecoicop2_code] ?? 0;
            return (
              <div
                key={cat.ecoicop2_code}
                className="grid grid-cols-[1fr_auto] items-center gap-3 sm:grid-cols-[220px_1fr_auto_auto]"
              >
                <div className="flex items-center gap-2 text-sm">
                  <span
                    className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: colorByCode[cat.ecoicop2_code] }}
                  />
                  {cat.name_en}
                </div>
                <input
                  type="range"
                  min={0}
                  max={SLIDER_MAX}
                  step={0.1}
                  value={weight}
                  onChange={(e) =>
                    setWeights((w) => ({ ...w, [cat.ecoicop2_code]: Number(e.target.value) }))
                  }
                  className="w-full"
                />
                <div className="w-20 text-right text-sm tabular-nums text-neutral-400">
                  {weight.toFixed(1)}
                  <span className="text-neutral-600"> / {cat.hicp_weight?.toFixed(1) ?? "0.0"}</span>
                </div>
                <div className="w-16 text-right text-sm font-medium tabular-nums text-neutral-200">
                  {share.toFixed(1)}%
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <div className="text-center">
        <a href="/" className="text-sm text-neutral-400 hover:text-neutral-200">
          ← Back to dashboard
        </a>
      </div>
    </main>
  );
}
