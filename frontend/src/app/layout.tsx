// Root layout: wraps every page with the <html> and <body> tags, and loads the fonts.
import type { Metadata } from "next";
import { Inter, Noto_Sans_Devanagari } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";

// next/font downloads the fonts at build time and serves them from our own origin.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter" });
// Only the Devanagari subset. Its @font-face has a unicode-range, so the browser downloads
// it only when Hindi characters appear. preload: false keeps English pages from fetching it.
const devanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "600", "700"],
  variable: "--font-devanagari",
  preload: false,
});

export const metadata: Metadata = {
  title: "SevaDesk",
  description: "SevaDesk",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={cn("h-full antialiased", inter.variable, devanagari.variable)}>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
