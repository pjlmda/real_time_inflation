import type { SeriesPoint } from "../lib/types";
import LineChart from "./LineChart";

export default function TimeSeriesChart({ data }: { data: SeriesPoint[] }) {
  return (
    <LineChart
      dates={data.map((d) => d.as_of_date)}
      series={[
        // Categorical slots 1/2 from the project's validated palette, fixed
        // order — not arbitrary Tailwind defaults.
        { label: "Daily index", color: "#3987e5", values: data.map((d) => d.index_value) },
        { label: "7-day average", color: "#d95926", values: data.map((d) => d.index_value_ma7) },
      ]}
    />
  );
}
