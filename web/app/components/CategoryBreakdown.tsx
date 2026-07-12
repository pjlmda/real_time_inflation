import { memo, useMemo } from "react";
import type { CategoryRow } from "../lib/types";
import { formatNumber, formatPercent, rateColorClass } from "../lib/format";

function CategoryBreakdown({
  categories,
  country,
}: {
  categories: CategoryRow[];
  country: string;
}) {
  // categories is a static server-fetched prop that never changes within
  // this client subtree — this component still re-renders on every
  // Dashboard basis/family toggle (it's part of that "use client" tree even
  // without its own directive), so avoid re-sorting on every one of those.
  const sorted = useMemo(
    () => [...categories].sort((a, b) => (b.hicp_weight ?? 0) - (a.hicp_weight ?? 0)),
    [categories]
  );

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-medium">ECOICOP breakdown</h2>
          <p className="mt-1 text-sm text-neutral-400">
            Fixed-basket index per category, weighted by HICP importance.
          </p>
        </div>
        <a
          href={`/personalize?country=${country}`}
          className="shrink-0 rounded border border-neutral-700 px-3 py-1.5 text-sm text-neutral-300 hover:bg-neutral-800"
        >
          Personalize my rate
        </a>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-neutral-500">
            <tr>
              <th className="py-1 pr-4 font-normal">Category</th>
              <th className="py-1 pr-4 font-normal">HICP weight</th>
              <th
                className="py-1 pr-4 font-normal underline decoration-dotted decoration-neutral-600 cursor-help"
                title="Index = 100 on the day each category first entered the tracker (categories were added incrementally, so the base date differs per row — hover a value to see its exact base date)."
              >
                Index
              </th>
              <th className="py-1 pr-4 font-normal">Daily change</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((cat) => {
              const metric = cat.latest["fixed_basket_headline"];
              return (
                <tr key={cat.ecoicop2_code} className="border-t border-neutral-800">
                  <td className="py-2 pr-4">{cat.name_en}</td>
                  <td className="py-2 pr-4 tabular-nums text-neutral-400">
                    {formatNumber(cat.hicp_weight)}
                  </td>
                  <td
                    className="py-2 pr-4 tabular-nums cursor-help"
                    title={
                      metric && cat.base_date
                        ? `100 = index value on ${cat.base_date}, the day this category was first tracked`
                        : undefined
                    }
                  >
                    {formatNumber(metric?.index_value)}
                    {metric?.low_confidence && (
                      <span className="ml-1 rounded bg-yellow-900 px-1 text-xs text-yellow-300">low confidence</span>
                    )}
                  </td>
                  <td
                    className={`py-2 pr-4 tabular-nums ${rateColorClass(metric?.inflation_rate, {
                      unknown: "text-neutral-500",
                      neutral: "",
                    })}`}
                  >
                    {formatPercent(metric?.inflation_rate)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default memo(CategoryBreakdown);
