import type { StoreRow } from "../lib/types";

export default function StoreComparison({ stores }: { stores: StoreRow[] }) {
  const values = stores
    .map((s) => s.latest["fixed_basket_headline"]?.index_value)
    .filter((v): v is number => v != null);
  const maxDeviation = Math.max(1, ...values.map((v) => Math.abs(v - 100)));

  return (
    <section className="rounded-lg border border-neutral-800 p-5">
      <h2 className="text-lg font-medium">Store comparison</h2>
      <p className="mt-1 text-sm text-neutral-400">Fixed-basket index (headline) per store.</p>
      <div className="mt-4 space-y-3">
        {stores.map((store) => {
          const metric = store.latest["fixed_basket_headline"];
          const value = metric?.index_value ?? 100;
          const widthPct = Math.min(100, (Math.abs(value - 100) / maxDeviation) * 100);
          return (
            <div key={store.slug} className="flex items-center gap-3 text-sm">
              <span className="w-28 shrink-0">{store.name}</span>
              <div className="h-2 flex-1 rounded bg-neutral-800">
                <div
                  className={`h-2 rounded ${value >= 100 ? "bg-red-400" : "bg-green-400"}`}
                  style={{ width: `${widthPct}%` }}
                />
              </div>
              <span className="w-16 shrink-0 text-right tabular-nums">{value.toFixed(2)}</span>
              {store.last_scrape && (
                <span
                  className={`w-16 shrink-0 rounded px-1 text-center text-xs ${
                    store.last_scrape.status === "success" ? "text-neutral-500" : "bg-yellow-900 text-yellow-300"
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
