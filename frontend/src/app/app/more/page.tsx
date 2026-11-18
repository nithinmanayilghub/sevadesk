// The More page (/app/more): links to the settings pages this User may open, and log out.
import type { Metadata } from "next";
import { LogoutButton } from "@/components/LogoutButton";
import { SettingsLinks } from "@/components/SettingsLinks";

export const metadata: Metadata = { title: "More · SevaDesk" };

export default function MorePage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">More</h1>
      <SettingsLinks />
      <LogoutButton />
    </main>
  );
}
