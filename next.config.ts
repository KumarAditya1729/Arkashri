import type { NextConfig } from "next";

const nextConfig = {
  output: "standalone",   // Required for Docker 3-stage build
} satisfies Record<string, unknown>;

export default nextConfig as NextConfig;
