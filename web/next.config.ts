import type { NextConfig } from "next";

// The /api/* -> Python function rewrite lives in vercel.json instead of here
// (see that file's comment for why) — nothing else needs custom Next.js
// config for this project.
const nextConfig: NextConfig = {};

export default nextConfig;
