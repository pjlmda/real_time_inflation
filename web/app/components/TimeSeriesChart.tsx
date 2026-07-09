import type { SeriesPoint } from "../lib/types";
import LineChart from "./LineChart";

export default function TimeSeriesChart({ data }: { data: SeriesPoint[] }) {
  return (
    <LineChart
      dates={data.map((d) => d.as_of_date)}
      series={[
        { label: "Daily index", color: "#60a5fa", values: data.map((d) => d.index_value) },
        { label: "7-day average", color: "#f472b6", values: data.map((d) => d.index_value_ma7) },
      ]}
    />
  );
}
