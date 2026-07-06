import type { HealthResponse } from "../lib/types";

function formatTime(iso: string | null): string {
  if (!iso) return "never";
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default function CoverageBanner({ health }: { health: HealthResponse }) {
  return (
    <section
      className={`rounded-lg border p-4 text-sm ${
        health.healthy ? "border-green-900 bg-green-950/40" : "border-yellow-900 bg-yellow-950/40"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-medium">
          {health.healthy ? "All systems healthy" : "Some data may be stale or low-confidence"}
        </span>
        <span className="text-neutral-400">
          Metrics computed: {formatTime(health.compute.latest_computed_at)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-4 text-neutral-400">
        {Object.entries(health.stores).map(([slug, modes]) => (
          <span key={slug}>
            {slug}: basket {modes.basket?.status ?? "—"} ({((modes.basket?.coverage ?? 0) * 100).toFixed(0)}%)
          </span>
        ))}
      </div>
    </section>
  );
}
