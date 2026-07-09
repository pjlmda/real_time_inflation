import { useRef, useState } from "react";
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

export default function TimeSeriesChart({ data }: { data: SeriesPoint[] }) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

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

  const rawPoints = pointsFor(rawValues, min, max);
  const ma7Points = pointsFor(ma7Values, min, max);
  const rawLine = toPolyline(rawPoints);
  const ma7Line = toPolyline(ma7Points);

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
    const i = Math.round(fraction * (data.length - 1));
    return Math.min(data.length - 1, Math.max(0, i));
  }

  const hovered = hoverIndex !== null ? data[hoverIndex] : null;
  const hoverX = hoverIndex !== null ? PADDING.left + (hoverIndex / (data.length - 1)) * innerWidth : null;
  const hoverRawPoint = hoverIndex !== null ? rawPoints[hoverIndex] : null;
  const hoverMa7Point = hoverIndex !== null ? ma7Points[hoverIndex] : null;

  // Tooltip position as a CSS percentage of the responsive container, derived
  // from the same SVG-unit coordinates the chart itself is drawn in.
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
        {hoverX !== null && (
          <line
            x1={hoverX}
            x2={hoverX}
            y1={PADDING.top}
            y2={HEIGHT - PADDING.bottom}
            stroke="#666"
            strokeWidth={1}
          />
        )}
        {hoverRawPoint && (
          <circle cx={hoverRawPoint[0]} cy={hoverRawPoint[1]} r={3.5} fill="#60a5fa" />
        )}
        {hoverMa7Point && (
          <circle cx={hoverMa7Point[0]} cy={hoverMa7Point[1]} r={3.5} fill="#f472b6" />
        )}
        <text x={PADDING.left} y={HEIGHT - 4} fontSize={11} fill="#999">
          {data[0].as_of_date}
        </text>
        <text x={WIDTH - PADDING.right} y={HEIGHT - 4} textAnchor="end" fontSize={11} fill="#999">
          {data[data.length - 1].as_of_date}
        </text>
      </svg>
      {hovered && tooltipLeftPct !== null && (
        <div
          className="pointer-events-none absolute top-1 rounded border border-neutral-700 bg-neutral-900 px-2 py-1 text-xs shadow-lg"
          style={{
            left: `${tooltipLeftPct}%`,
            transform: tooltipFlip ? "translateX(-100%)" : "translateX(0)",
            marginLeft: tooltipFlip ? -8 : 8,
          }}
        >
          <div className="text-neutral-400">{hovered.as_of_date}</div>
          <div className="text-[#60a5fa]">
            Daily: {hovered.index_value != null ? hovered.index_value.toFixed(decimals) : "—"}
          </div>
          <div className="text-[#f472b6]">
            7-day avg: {hovered.index_value_ma7 != null ? hovered.index_value_ma7.toFixed(decimals) : "—"}
          </div>
        </div>
      )}
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
