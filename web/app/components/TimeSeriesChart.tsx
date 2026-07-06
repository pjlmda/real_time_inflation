import type { SeriesPoint } from "../lib/types";

// Hand-rolled SVG line chart, not a charting library — Recharts 3 + Next.js
// 16 (Turbopack) + React 19 hit a silent rendering failure here (the
// recharts-wrapper div mounted with correct dimensions, but its internal
// <svg> never appeared, with no thrown error to chase). For a chart this
// simple (two lines, a few dozen points), plain SVG is fewer moving parts
// and has no third-party version-compatibility surface at all.

const WIDTH = 900;
const HEIGHT = 260;
const PADDING = { top: 10, right: 10, bottom: 24, left: 56 };

function buildPoints(values: (number | null)[], min: number, max: number): string {
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const range = max - min || 1;
  return values
    .map((v, i) => {
      if (v === null) return null;
      const x = PADDING.left + (values.length === 1 ? 0 : (i / (values.length - 1)) * innerWidth);
      const y = PADDING.top + innerHeight - ((v - min) / range) * innerHeight;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .filter((p): p is string => p !== null)
    .join(" ");
}

export default function TimeSeriesChart({ data }: { data: SeriesPoint[] }) {
  if (data.length < 2) {
    return (
      <p className="text-sm text-neutral-500">
        Not enough history yet to chart a trend — check back after a few more days.
      </p>
    );
  }

  const rawValues = data.map((d) => d.index_value);
  const ma7Values = data.map((d) => d.index_value_ma7);
  const allValues = [...rawValues, ...ma7Values].filter((v): v is number => v !== null);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);

  const rawLine = buildPoints(rawValues, min, max);
  const ma7Line = buildPoints(ma7Values, min, max);

  // The index often barely moves day-to-day (e.g. 99.99 vs 100.00) — a fixed
  // 1-decimal label would round every gridline to the same value, making the
  // axis look broken. Use however many decimals it takes to distinguish
  // min from max, up to a sane cap.
  const range = max - min;
  const decimals = range === 0 ? 2 : Math.min(4, Math.max(2, Math.ceil(-Math.log10(range)) + 1));

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full" style={{ height: 260 }}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = PADDING.top + t * (HEIGHT - PADDING.top - PADDING.bottom);
          const value = max - t * (max - min);
          return (
            <g key={t}>
              <line
                x1={PADDING.left}
                x2={WIDTH - PADDING.right}
                y1={y}
                y2={y}
                stroke="#2a2a2a"
                strokeDasharray="3 3"
              />
              <text x={PADDING.left - 6} y={y + 4} textAnchor="end" fontSize={11} fill="#999">
                {value.toFixed(decimals)}
              </text>
            </g>
          );
        })}
        <polyline points={rawLine} fill="none" stroke="#60a5fa" strokeWidth={1.5} />
        <polyline points={ma7Line} fill="none" stroke="#f472b6" strokeWidth={2.5} />
        <text x={PADDING.left} y={HEIGHT - 4} fontSize={11} fill="#999">
          {data[0].as_of_date}
        </text>
        <text x={WIDTH - PADDING.right} y={HEIGHT - 4} textAnchor="end" fontSize={11} fill="#999">
          {data[data.length - 1].as_of_date}
        </text>
      </svg>
      <div className="mt-2 flex gap-4 text-xs text-neutral-400">
        <span>
          <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#60a5fa]" />
          Daily index
        </span>
        <span>
          <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#f472b6]" />
          7-day average
        </span>
      </div>
    </div>
  );
}
