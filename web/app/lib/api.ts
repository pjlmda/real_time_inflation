import type {
  CategoryRow,
  FuelRow,
  HealthResponse,
  LatestOverallResponse,
  ProductRow,
  SeriesPoint,
  StoreRow,
} from "./types";

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

export const getHealth = () => apiGet<HealthResponse>("/api/health");
export const getLatestOverall = () => apiGet<LatestOverallResponse>("/api/inflation/latest");
export const getCategories = () => apiGet<CategoryRow[]>("/api/categories");
export const getStores = () => apiGet<StoreRow[]>("/api/stores");
export const getProducts = () => apiGet<ProductRow[]>("/api/products");
export const getFuelLatest = () => apiGet<FuelRow[]>("/api/fuel/latest");

export function getSeries(params: {
  family?: "fixed_basket" | "category_avg";
  dimension?: "overall" | "category" | "store";
  value?: string;
  period?: "daily" | "weekly" | "monthly" | "yearly";
  basis?: "headline" | "effective";
}): Promise<SeriesPoint[]> {
  const query = new URLSearchParams({
    family: params.family ?? "fixed_basket",
    dimension: params.dimension ?? "overall",
    value: params.value ?? "ALL",
    period: params.period ?? "daily",
    basis: params.basis ?? "headline",
  });
  return apiGet<SeriesPoint[]>(`/api/inflation/series?${query.toString()}`);
}
