import { memo } from "react";
import type { HealthResponse } from "../lib/types";

function formatTime(iso: string | null): string {
  if (!iso) return "never";
  // Explicit timeZone (matching the rest of the project's Europe/Lisbon
  // convention) is required here, not just cosmetic — without it, this
  // renders differently on the server (Vercel, UTC) vs. whatever timezone
  // the visiting browser is in, which is a real Next.js hydration mismatch
  // (React error #418), not just a display inconsistency.
  return new Date(iso).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Europe/Lisbon",
  });
}

function CoverageBanner({ health }: { health: HealthResponse }) {
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
            {modes.basket?.blocked && (
              <span className="ml-1 rounded bg-red-900 px-1 text-xs text-red-300">blocked</span>
            )}
          </span>
        ))}
      </div>
    </section>
  );
}

export default memo(CoverageBanner);
