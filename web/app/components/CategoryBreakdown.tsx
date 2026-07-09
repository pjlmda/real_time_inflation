import type { CategoryRow } from "../lib/types";

export default function CategoryBreakdown({ categories }: { categories: CategoryRow[] }) {
  const sorted = [...categories].sort((a, b) => (b.hicp_weight ?? 0) - (a.hicp_weight ?? 0));

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-medium">ECOICOP breakdown</h2>
      <p className="mt-1 text-sm text-neutral-400">
        Fixed-basket index per category, weighted by HICP importance.
      </p>
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
                    {cat.hicp_weight?.toFixed(2) ?? "—"}
                  </td>
                  <td
                    className="py-2 pr-4 tabular-nums cursor-help"
                    title={
                      metric && cat.base_date
                        ? `100 = index value on ${cat.base_date}, the day this category was first tracked`
                        : undefined
                    }
                  >
                    {metric ? metric.index_value?.toFixed(2) : "—"}
                    {metric?.low_confidence && (
                      <span className="ml-1 rounded bg-yellow-900 px-1 text-xs text-yellow-300">low confidence</span>
                    )}
                  </td>
                  <td
                    className={`py-2 pr-4 tabular-nums ${
                      metric?.inflation_rate == null
                        ? "text-neutral-500"
                        : metric.inflation_rate > 0
                          ? "text-red-400"
                          : metric.inflation_rate < 0
                            ? "text-green-400"
                            : ""
                    }`}
                  >
                    {metric?.inflation_rate != null ? `${metric.inflation_rate.toFixed(2)}%` : "—"}
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
