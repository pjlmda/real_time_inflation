import Dashboard from "./components/Dashboard";
import {
  DEFAULT_COUNTRY,
  getCategories,
  getCountries,
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

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ country?: string }>;
}) {
  const { country: countryParam } = await searchParams;
  const country = countryParam ?? DEFAULT_COUNTRY;

  const [countries, health, latest, categories, stores, fuel, seriesHeadline, seriesEffective, seriesCategoryAvg] =
    await Promise.all([
      getCountries(),
      getHealth(country),
      getLatestOverall(country),
      getCategories(country),
      getStores(country),
      getFuelLatest(country),
      getSeries({ country, family: "fixed_basket", basis: "headline" }),
      getSeries({ country, family: "fixed_basket", basis: "effective" }),
      getSeries({ country, family: "category_avg", basis: "effective" }),
    ]);

  return (
    <Dashboard
      country={country}
      countries={countries}
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
