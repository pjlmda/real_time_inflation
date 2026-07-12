import type {
  CategoryRow,
  CategorySeriesBulk,
  CountryInfo,
  FuelRow,
  HealthResponse,
  LatestOverallResponse,
  SeriesPoint,
  StoreRow,
} from "./types";

export const DEFAULT_COUNTRY = "PT";

function apiBaseUrl(): string {
  // Explicit override always wins (used for local dev, pointed at a
  // separately-running uvicorn instance). On Vercel, both Next.js and the
  // FastAPI function share one deployment, so VERCEL_URL resolves it with
  // no extra manual env var needed beyond SUPABASE_URL/SERVICE_KEY.
  if (process.env.API_BASE_URL) return process.env.API_BASE_URL;
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://localhost:8123";
}

async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${apiBaseUrl()}${path}`, { next: { revalidate: 3600 } });
  if (!res.ok) {
    throw new Error(`API request failed: ${path} -> ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// /api/countries is deliberately not itself country-scoped (see
// web/api/index.py) — it's what populates the switcher, so it takes no
// country param.
export const getCountries = () => apiGet<CountryInfo[]>("/api/countries");

export const getHealth = (country: string) => apiGet<HealthResponse>(`/api/health?country=${country}`);
export const getLatestOverall = (country: string) =>
  apiGet<LatestOverallResponse>(`/api/inflation/latest?country=${country}`);
export const getCategories = (country: string) => apiGet<CategoryRow[]>(`/api/categories?country=${country}`);
export const getStores = (country: string) => apiGet<StoreRow[]>(`/api/stores?country=${country}`);
export const getFuelLatest = (country: string) => apiGet<FuelRow[]>(`/api/fuel/latest?country=${country}`);

export function getSeries(params: {
  country: string;
  family?: "fixed_basket" | "category_avg";
  dimension?: "overall" | "category" | "store";
  value?: string;
  period?: "daily" | "weekly" | "monthly" | "yearly";
  basis?: "headline" | "effective";
}): Promise<SeriesPoint[]> {
  const query = new URLSearchParams({
    country: params.country,
    family: params.family ?? "fixed_basket",
    dimension: params.dimension ?? "overall",
    value: params.value ?? "ALL",
    period: params.period ?? "daily",
    basis: params.basis ?? "headline",
  });
  return apiGet<SeriesPoint[]>(`/api/inflation/series?${query.toString()}`);
}

export function getSeriesBulk(params: {
  country: string;
  family?: "fixed_basket" | "category_avg";
  period?: "daily" | "weekly" | "monthly" | "yearly";
  basis?: "headline" | "effective";
}): Promise<CategorySeriesBulk> {
  const query = new URLSearchParams({
    country: params.country,
    family: params.family ?? "fixed_basket",
    period: params.period ?? "daily",
    basis: params.basis ?? "headline",
  });
  return apiGet<CategorySeriesBulk>(`/api/inflation/series/bulk?${query.toString()}`);
}
