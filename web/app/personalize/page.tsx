import PersonalizeDashboard from "./PersonalizeDashboard";
import { getCategories, getSeries, getSeriesBulk } from "../lib/api";

// Same reasoning as app/page.tsx: the API function this fetches from is
// built/deployed alongside this page, so it can't be prerendered at build
// time.
export const dynamic = "force-dynamic";

export default async function PersonalizePage({
  searchParams,
}: {
  searchParams: Promise<{ w?: string }>;
}) {
  const [{ w }, categories, bulkSeries, officialSeries] = await Promise.all([
    searchParams,
    getCategories(),
    getSeriesBulk({ family: "fixed_basket", basis: "headline" }),
    getSeries({ family: "fixed_basket", basis: "headline" }),
  ]);

  return (
    <PersonalizeDashboard
      categories={categories}
      bulkSeries={bulkSeries}
      officialSeries={officialSeries}
      initialWeightParam={w ?? null}
    />
  );
}
