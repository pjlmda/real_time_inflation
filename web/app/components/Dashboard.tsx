"use client";

import { useState } from "react";
import type {
  CategoryRow,
  FuelRow,
  HealthResponse,
  LatestOverallResponse,
  SeriesPoint,
  StoreRow,
} from "../lib/types";
import CoverageBanner from "./CoverageBanner";
import FuelPanel from "./FuelPanel";
import GapCard from "./GapCard";
import HeadlineCard from "./HeadlineCard";
import CategoryBreakdown from "./CategoryBreakdown";
import StoreComparison from "./StoreComparison";
import TimeSeriesChart from "./TimeSeriesChart";

type Basis = "headline" | "effective";
type Family = "fixed_basket" | "category_avg";

interface Props {
  health: HealthResponse;
  latest: LatestOverallResponse;
  categories: CategoryRow[];
  stores: StoreRow[];
  fuel: FuelRow[];
  series: {
    fixed_basket_headline: SeriesPoint[];
    fixed_basket_effective: SeriesPoint[];
    category_avg_effective: SeriesPoint[];
  };
}

export default function Dashboard({ health, latest, categories, stores, fuel, series }: Props) {
  const [basis, setBasis] = useState<Basis>("headline");
  const [family, setFamily] = useState<Family>("fixed_basket");

  const activeSeries =
    family === "category_avg" ? series.category_avg_effective : series[`fixed_basket_${basis}`];

  return (
    <main className="mx-auto max-w-5xl px-4 py-10 space-y-8">
      <header>
        <h1 className="text-2xl font-semibold">Portugal Real-Time Inflation Tracker</h1>
        <p className="text-sm text-neutral-400">
          Daily grocery &amp; fuel inflation, methodologically aligned with INE/Eurostat HICP.
        </p>
      </header>

      <CoverageBanner health={health} />

      <HeadlineCard latest={latest} basis={basis} onBasisChange={setBasis} />

      <GapCard latest={latest} />

      <section className="rounded-lg border border-neutral-800 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-medium">Index over time</h2>
          <div className="flex gap-2 text-sm">
            <FamilyToggle family={family} onChange={setFamily} />
          </div>
        </div>
        <TimeSeriesChart data={activeSeries} />
      </section>

      <CategoryBreakdown categories={categories} />

      <StoreComparison stores={stores} />

      <FuelPanel fuel={fuel} />
    </main>
  );
}

function FamilyToggle({ family, onChange }: { family: Family; onChange: (f: Family) => void }) {
  return (
    <div className="inline-flex overflow-hidden rounded border border-neutral-700">
      {(["fixed_basket", "category_avg"] as Family[]).map((f) => (
        <button
          key={f}
          onClick={() => onChange(f)}
          className={`px-3 py-1 ${
            family === f ? "bg-neutral-100 text-neutral-900" : "bg-transparent text-neutral-300"
          }`}
        >
          {f === "fixed_basket" ? "Fixed basket" : "Category average"}
        </button>
      ))}
    </div>
  );
}
