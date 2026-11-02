// Root layout: wraps every page with the <html> and <body> tags and sets the page title.
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SevaDesk",
  description: "SevaDesk",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
