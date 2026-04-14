import type { NextConfig } from "next";

const nextConfig = {
  output: "standalone",   // Required for Docker 3-stage build
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
} satisfies Record<string, unknown>;

export default nextConfig as NextConfig;
