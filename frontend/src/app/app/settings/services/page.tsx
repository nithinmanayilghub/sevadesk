// Settings → Services (/app/settings/services): Owner only (lib/pages.ts; the backend checks again).
import type { Metadata } from "next";
import { ServicesSettings } from "@/components/ServicesSettings";

export const metadata: Metadata = { title: "Services · SevaDesk" };

export default function ServicesPage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Services</h1>
      <ServicesSettings />
    </main>
  );
}
