# Web app (Phase 3)

Next.js frontend + FastAPI backend (`api/`), deployed together as one Vercel
project with **Root Directory set to `web/`**.

## Local dev

1. API (from the repo root, so it picks up the root `.env`):
   ```
   uv run --with fastapi --with uvicorn --with supabase --with python-dotenv \
     uvicorn api.index:app --reload --port 8123 --app-dir web
   ```
2. Frontend (from `web/`):
   ```
   npm install
   npm run dev
   ```
   The frontend defaults to `http://localhost:8123` for API calls (see
   `app/lib/api.ts`) — override with `API_BASE_URL` in `web/.env.local` if
   running the API on a different port.

## Production

Vercel builds `api/` (via `api/requirements.txt`) as one Python serverless
function and the Next.js app together. Required environment variables (set
in the Vercel project, not committed): `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`.
`API_BASE_URL` does not need to be set in production — it resolves
automatically via Vercel's `VERCEL_URL`.
