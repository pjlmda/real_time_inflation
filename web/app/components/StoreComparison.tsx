import { memo, useMemo } from "react";
import type { StoreRow } from "../lib/types";

function StoreComparison({ stores }: { stores: StoreRow[] }) {
  // stores is a static server-fetched prop — avoid recomputing this on
  // every Dashboard basis/family toggle re-render (see CategoryBreakdown's
  // identical reasoning for the same pattern).
  const maxDeviation = useMemo(() => {
    const values = stores
      .map((s) => s.latest["fixed_basket_headline"]?.index_value)
      .filter((v): v is number => v != null);
    return Math.max(1, ...values.map((v) => Math.abs(v - 100)));
  }, [stores]);

  return (
    <section className="rounded-xl border border-hairline bg-surface p-5 sm:p-6">
      <h2 className="text-base font-medium text-ink">Store comparison</h2>
      <p className="mt-1 text-sm text-ink2">Fixed-basket index (headline) per store.</p>
      <div className="mt-4 space-y-3">
        {stores.map((store) => {
          const metric = store.latest["fixed_basket_headline"];
          const value = metric?.index_value ?? 100;
          const widthPct = Math.min(100, (Math.abs(value - 100) / maxDeviation) * 100);
          return (
            <div key={store.slug} className="flex items-center gap-3 text-sm">
              <span className="w-28 shrink-0 text-ink2">{store.name}</span>
              <div className="h-1.5 flex-1 rounded-full bg-surface2">
                <div
                  className={`h-1.5 rounded-full ${value >= 100 ? "bg-bad" : "bg-good"}`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span className="w-16 shrink-0 text-right tabular-nums text-ink">{value.toFixed(2)}</span>
              {store.last_scrape && (
                <span
                  className={`w-16 shrink-0 rounded px-1 text-center text-xs ${
                    store.last_scrape.status === "success" ? "text-ink3" : "bg-warn/15 text-warn"
                  }`}
                >
                  {store.last_scrape.status}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export default memo(StoreComparison);
