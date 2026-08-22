import { useRef, useState } from "react";

// Hand-rolled SVG line chart, not a charting library — Recharts 3 + Next.js
// 16 (Turbopack) + React 19 hit a silent rendering failure here (the
// recharts-wrapper div mounted with correct dimensions, but its internal
// <svg> never appeared, with no thrown error to chase). For a chart this
// simple (a handful of lines, a few dozen points), plain SVG is fewer moving
// parts and has no third-party version-compatibility surface at all.
//
// Generic over an arbitrary number of named/colored lines sharing one x-axis
// (dates) so both the fixed-basket-vs-MA7 chart and the personalized-weights
// trend chart can reuse the same geometry and hover behavior.

const WIDTH = 900;
const HEIGHT = 260;
const PADDING = { top: 10, right: 10, bottom: 24, left: 56 };

export interface LineSeries {
  label: string;
  color: string;
  values: (number | null)[];
}

function pointsFor(values: (number | null)[], min: number, max: number): (readonly [number, number] | null)[] {
  const innerWidth = WIDTH - PADDING.left - PADDING.right;
  const innerHeight = HEIGHT - PADDING.top - PADDING.bottom;
  const range = max - min || 1;
  return values.map((v, i) => {
    if (v === null) return null;
    const x = PADDING.left + (values.length === 1 ? 0 : (i / (values.length - 1)) * innerWidth);
    const y = PADDING.top + innerHeight - ((v - min) / range) * innerHeight;
    return [x, y] as const;
  });
}

function toPolyline(points: (readonly [number, number] | null)[]): string {
  return points
    .filter((p): p is readonly [number, number] => p !== null)
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
}

export default function LineChart({
  dates,
  series,
  emptyMessage = "Not enough history yet to chart a trend — check back after a few more days.",
}: {
  dates: string[];
  series: LineSeries[];
  emptyMessage?: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  if (dates.length < 2) {
    return <p className="text-sm text-ink3">{emptyMessage}</p>;
  }

  const allValues = series.flatMap((s) => s.values).filter((v): v is number => v !== null);
  const min = allValues.length ? Math.min(...allValues) : 0;
  const max = allValues.length ? Math.max(...allValues) : 1;

  const seriesPoints = series.map((s) => pointsFor(s.values, min, max));

  // The index often barely moves day-to-day (e.g. 99.99 vs 100.00) — a fixed
  // 1-decimal label would round every gridline to the same value, making the
  // axis look broken. Use however many decimals it takes to distinguish
  // min from max, up to a sane cap.
  const range = max - min;
  const decimals = range === 0 ? 2 : Math.min(4, Math.max(2, Math.ceil(-Math.log10(range)) + 1));

  const innerWidth = WIDTH - PADDING.left - PADDING.right;

  function indexFromClientX(clientX: number): number {
    const rect = svgRef.current!.getBoundingClientRect();
    const fractionX = (clientX - rect.left) / rect.width;
    const svgX = fractionX * WIDTH;
    const fraction = (svgX - PADDING.left) / innerWidth;
    const i = Math.round(fraction * (dates.length - 1));
    return Math.min(dates.length - 1, Math.max(0, i));
  }

  const hoverX = hoverIndex !== null ? PADDING.left + (hoverIndex / (dates.length - 1)) * innerWidth : null;

  const tooltipLeftPct = hoverX !== null ? (hoverX / WIDTH) * 100 : null;
  const tooltipFlip = tooltipLeftPct !== null && tooltipLeftPct > 65;

  return (
    <div className="w-full relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full"
        style={{ height: 260 }}
        onMouseMove={(e) => setHoverIndex(indexFromClientX(e.clientX))}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((t) => {
          const y = PADDING.top + t * (HEIGHT - PADDING.top - PADDING.bottom);
          const value = max - t * (max - min);
          return (
            <g key={t}>
              {/* Hairline, solid — never dashed, kept recessive against the data. */}
              <line x1={PADDING.left} x2={WIDTH - PADDING.right} y1={y} y2={y} stroke="#2c2c2a" strokeWidth={1} />
              <text x={PADDING.left - 6} y={y + 4} textAnchor="end" fontSize={11} fill="#898781">
                {value.toFixed(decimals)}
              </text>
            </g>
          );
        })}
        {series.map((s, si) => (
          <polyline
            key={s.label}
            points={toPolyline(seriesPoints[si])}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        ))}
        {hoverX !== null && (
          <line
            x1={hoverX}
            x2={hoverX}
            y1={PADDING.top}
            y2={HEIGHT - PADDING.bottom}
            stroke="#898781"
            strokeWidth={1}
          />
        )}
        {hoverIndex !== null &&
          series.map((s, si) => {
            const p = seriesPoints[si][hoverIndex];
            // r=4 (8px) with a surface-color ring so the marker stays legible
            // where two series cross or overlap.
            return p ? (
              <circle key={s.label} cx={p[0]} cy={p[1]} r={4} fill={s.color} stroke="#1a1a19" strokeWidth={2} />
            ) : null;
          })}
        <text x={PADDING.left} y={HEIGHT - 4} fontSize={11} fill="#898781">
          {dates[0]}
        </text>
        <text x={WIDTH - PADDING.right} y={HEIGHT - 4} textAnchor="end" fontSize={11} fill="#898781">
          {dates[dates.length - 1]}
        </text>
      </svg>
      {hoverIndex !== null && tooltipLeftPct !== null && (
        <div
          className="pointer-events-none absolute top-1 rounded-md border border-hairline bg-surface px-2.5 py-1.5 text-xs shadow-lg"
          style={{
            left: `${tooltipLeftPct}%`,
            transform: tooltipFlip ? "translateX(-100%)" : "translateX(0)",
            marginLeft: tooltipFlip ? -8 : 8,
          }}
        >
          <div className="text-ink3">{dates[hoverIndex]}</div>
          {series.map((s) => {
            const v = s.values[hoverIndex];
            return (
              <div key={s.label} className="flex items-center gap-1.5 text-ink2">
                {/* Identity rides the dot, not the text color — text stays a neutral ink token. */}
                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s.color }} />
                {s.label}: <span className="tabular-nums text-ink">{v != null ? v.toFixed(decimals) : "—"}</span>
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-2 flex gap-4 text-xs text-ink2">
        {series.map((s) => (
          <span key={s.label} className="inline-flex items-center">
            <span className="mr-1.5 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  );
}
