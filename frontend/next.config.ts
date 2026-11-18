// Next.js settings. "standalone" builds a small self-contained server for Docker.
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // The invite page address holds a secret token (/invite/<token>). This header tells the
  // browser to send no Referer from it, from the very first request (story 2.5). The page's
  // <meta name="referrer"> does the same, but only after the browser has read the page.
  async headers() {
    return [{ source: "/invite/:path*", headers: [{ key: "Referrer-Policy", value: "no-referrer" }] }];
  },
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
