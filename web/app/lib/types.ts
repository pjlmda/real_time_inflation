// Mirrors web/api/db.py's `_shape_metric_row` and each endpoint's response shape.

export interface MetricPoint {
  index_value: number | null;
  index_value_ma7: number | null;
  inflation_rate: number | null;
  n_products: number | null;
  coverage: number | null;
  low_confidence: boolean;
}

export interface SeriesPoint extends MetricPoint {
  as_of_date: string;
}

type PeriodMap = Record<"daily" | "weekly" | "monthly" | "yearly", MetricPoint>;

export interface LatestOverallResponse {
  as_of_date: string | null;
  fixed_basket: { headline?: PeriodMap; effective?: PeriodMap };
  category_avg: { effective?: PeriodMap };
}

export interface CategoryRow {
  ecoicop2_code: string;
  name_pt: string;
  name_en: string;
  hicp_weight: number | null;
  latest: Record<string, MetricPoint>;
  base_date: string | null;
}

export interface StoreRow {
  slug: string;
  name: string;
  latest: Record<string, MetricPoint>;
  last_scrape: { status: string; coverage: number; finished_at: string } | null;
}

export interface ProductListing {
  store: string;
  url: string;
  latest_price: {
    listing_id: number;
    scrape_date: string;
    price: number;
    regular_price: number;
    price_per_unit: number;
    unit_basis: string;
    is_promotion: boolean;
  } | null;
}

export interface ProductRow {
  canonical_name: string;
  brand: string | null;
  category: string | null;
  package_size: number;
  package_unit: string;
  listings: ProductListing[];
}

export interface FuelRow {
  fuel_type: "gasoline_95" | "diesel" | "lpg_auto";
  scrape_date: string;
  price: number;
  unit: string;
  week_ago_price: number | null;
}

interface ScrapeRunSummary {
  status: string;
  coverage: number;
  finished_at: string;
  blocked: boolean;
}

export interface BulkSeriesPoint {
  as_of_date: string;
  index_value: number | null;
  index_value_ma7: number | null;
}

// Keyed by ecoicop2_code — see /api/inflation/series/bulk.
export type CategorySeriesBulk = Record<string, BulkSeriesPoint[]>;

export interface HealthResponse {
  healthy: boolean;
  stores: Record<string, { basket: ScrapeRunSummary | null; category: ScrapeRunSummary | null }>;
  compute: { latest_computed_at: string | null; stale: boolean };
  fuel: { latest_fetched_at: string | null; stale: boolean };
}
