import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle so the Docker runtime stage stays slim.
  output: "standalone",
};

export default nextConfig;
