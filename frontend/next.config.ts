// Next.js settings. "standalone" builds a small self-contained server for Docker.
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Runs Tailwind on CSS files (setup that create-next-app generated).
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
