import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",   // Required for Docker 3-stage build
};

export default nextConfig;
