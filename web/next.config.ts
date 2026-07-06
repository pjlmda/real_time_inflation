import type { NextConfig } from "next";

// In production (Vercel), the FastAPI serverless function lives at
// web/api/index.py and is reached via /api/*. Locally, next.config's
// rewrite would need a running uvicorn instance at the same path, which
// isn't how local dev is done here (see app/lib/api.ts's separate
// API_BASE_URL) — so this rewrite is a production-only convenience,
// harmless in dev since nothing calls a relative /api/* path directly.
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: "/api/index" }];
  },
};

export default nextConfig;
