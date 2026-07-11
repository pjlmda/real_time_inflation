import PersonalizeDashboard from "./PersonalizeDashboard";
import { DEFAULT_COUNTRY, getCategories, getCountries, getSeries, getSeriesBulk } from "../lib/api";

// Same reasoning as app/page.tsx: the API function this fetches from is
// built/deployed alongside this page, so it can't be prerendered at build
// time.
export const dynamic = "force-dynamic";

export default async function PersonalizePage({
  searchParams,
}: {
  searchParams: Promise<{ w?: string; country?: string }>;
}) {
  const { w, country: countryParam } = await searchParams;
  const country = countryParam ?? DEFAULT_COUNTRY;

  const [countries, categories, bulkSeries, officialSeries] = await Promise.all([
    getCountries(),
    getCategories(country),
    getSeriesBulk({ country, family: "fixed_basket", basis: "headline" }),
    getSeries({ country, family: "fixed_basket", basis: "headline" }),
  ]);

  return (
    <PersonalizeDashboard
      country={country}
      countries={countries}
      categories={categories}
      bulkSeries={bulkSeries}
      officialSeries={officialSeries}
      initialWeightParam={w ?? null}
    />
  );
}
