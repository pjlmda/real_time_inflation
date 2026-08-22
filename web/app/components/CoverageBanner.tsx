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
      className={`rounded-xl border p-4 text-sm ${
        health.healthy ? "border-good/30 bg-good/10" : "border-warn/30 bg-warn/10"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className={`font-medium ${health.healthy ? "text-good" : "text-warn"}`}>
          {health.healthy ? "All systems healthy" : "Some data may be stale or low-confidence"}
        </span>
        <span className="text-ink3">
          Metrics computed: {formatTime(health.compute.latest_computed_at)}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-ink2">
        {Object.entries(health.stores).map(([slug, modes]) => (
          <span key={slug}>
            {slug}: basket {modes.basket?.status ?? "—"} ({((modes.basket?.coverage ?? 0) * 100).toFixed(0)}%)
            {modes.basket?.blocked && (
              <span className="ml-1 rounded bg-bad/20 px-1 text-xs text-bad">blocked</span>
            )}
          </span>
        ))}
      </div>
    </section>
  );
}

export default memo(CoverageBanner);
