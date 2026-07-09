// Small donut chart of each category's normalized share of the current
// weight mix. Always sums to a full circle by construction (it's drawn from
// normalized shares, the same renormalization weightedOverallIndex already
// does) — this is the visual answer to "do my sliders add up to 100%?"
// rather than a hard slider constraint, since the underlying math never
// actually required the raw sliders to sum to 100 in the first place.

const SIZE = 140;
const RADIUS = 52;
const STROKE = 20;
const CENTER = SIZE / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export interface WeightSlice {
  code: string;
  label: string;
  value: number;
  color: string;
}

export default function WeightPieChart({ slices }: { slices: WeightSlice[] }) {
  const total = slices.reduce((sum, s) => sum + Math.max(s.value, 0), 0);

  if (total <= 0) {
    return (
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="shrink-0">
        <circle cx={CENTER} cy={CENTER} r={RADIUS} fill="none" stroke="#2a2a2a" strokeWidth={STROKE} />
        <text x={CENTER} y={CENTER} textAnchor="middle" dominantBaseline="middle" fontSize={11} fill="#999">
          No weight set
        </text>
      </svg>
    );
  }

  let cumulative = 0;
  const arcs = slices
    .filter((s) => s.value > 0)
    .map((s) => {
      const fraction = s.value / total;
      const length = fraction * CIRCUMFERENCE;
      const arc = (
        <circle
          key={s.code}
          cx={CENTER}
          cy={CENTER}
          r={RADIUS}
          fill="none"
          stroke={s.color}
          strokeWidth={STROKE}
          strokeDasharray={`${length} ${CIRCUMFERENCE - length}`}
          strokeDashoffset={-cumulative}
        >
          <title>
            {s.label}: {(fraction * 100).toFixed(1)}%
          </title>
        </circle>
      );
      cumulative += length;
      return arc;
    });

  return (
    <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="shrink-0">
      <g transform={`rotate(-90 ${CENTER} ${CENTER})`}>{arcs}</g>
      <text x={CENTER} y={CENTER} textAnchor="middle" dominantBaseline="middle" fontSize={13} fill="#e5e5e5">
        100%
      </text>
    </svg>
  );
}
