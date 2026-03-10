import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // Required for Docker 3-stage build
  eslint: {
    ignoreDuringBuilds: true,
  },
  typescript: {
    ignoreBuildErrors: true,
  },
};

export default nextConfig;
