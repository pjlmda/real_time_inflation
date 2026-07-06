import Dashboard from "./components/Dashboard";
import {
  getCategories,
  getFuelLatest,
  getHealth,
  getLatestOverall,
  getSeries,
  getStores,
} from "./lib/api";

// Must render per-request, not prerender at build time — the API function
// this page fetches from doesn't exist yet during Vercel's build step
// (it's built/deployed in the same step as this page), so build-time
// prerendering would always fail. The per-fetch `revalidate: 3600` in
// app/lib/api.ts still caches each individual API response for an hour.
export const dynamic = "force-dynamic";

export default async function Home() {
  const [health, latest, categories, stores, fuel, seriesHeadline, seriesEffective, seriesCategoryAvg] =
    await Promise.all([
      getHealth(),
      getLatestOverall(),
      getCategories(),
      getStores(),
      getFuelLatest(),
      getSeries({ family: "fixed_basket", basis: "headline" }),
      getSeries({ family: "fixed_basket", basis: "effective" }),
      getSeries({ family: "category_avg", basis: "effective" }),
    ]);

  return (
    <Dashboard
      health={health}
      latest={latest}
      categories={categories}
      stores={stores}
      fuel={fuel}
      series={{
        fixed_basket_headline: seriesHeadline,
        fixed_basket_effective: seriesEffective,
        category_avg_effective: seriesCategoryAvg,
      }}
    />
  );
}
