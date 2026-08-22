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
    <section className="rounded-xl border border-hairline bg-surface p-5 sm:p-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-medium text-ink">ECOICOP breakdown</h2>
          <p className="mt-1 text-sm text-ink2">
            Fixed-basket index per category, weighted by HICP importance.
          </p>
        </div>
        <a
          href={`/personalize?country=${country}`}
          className="shrink-0 rounded-md border border-chart1/40 bg-chart1/10 px-3 py-1.5 text-sm font-medium text-chart1 transition-colors hover:bg-chart1/20"
        >
          Personalize my rate
        </a>
      </div>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-ink3">
            <tr>
              <th className="py-1 pr-4 font-normal">Category</th>
              <th className="py-1 pr-4 font-normal">HICP weight</th>
              <th
                className="py-1 pr-4 font-normal underline decoration-dotted decoration-ink3/60 cursor-help"
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
                <tr key={cat.ecoicop2_code} className="border-t border-hairline">
                  <td className="py-2 pr-4 text-ink">{cat.name_en}</td>
                  <td className="py-2 pr-4 tabular-nums text-ink2">
                    {formatNumber(cat.hicp_weight)}
                  </td>
                  <td
                    className="py-2 pr-4 tabular-nums text-ink cursor-help"
                    title={
                      metric && cat.base_date
                        ? `100 = index value on ${cat.base_date}, the day this category was first tracked`
                        : undefined
                    }
                  >
                    {formatNumber(metric?.index_value)}
                    {metric?.low_confidence && (
                      <span className="ml-1 rounded bg-warn/15 px-1 text-xs text-warn">low confidence</span>
                    )}
                  </td>
                  <td
                    className={`py-2 pr-4 tabular-nums ${rateColorClass(metric?.inflation_rate, {
                      unknown: "text-ink3",
                      neutral: "text-ink2",
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
