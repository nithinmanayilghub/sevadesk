"use client";
// Settings → Appearance (story 2.6, UX-DR3): System, Light or Dark, saved per User.
// The new theme shows at once (an "optimistic" change); then we save it. If the save fails,
// the old theme comes back and we say so. One save at a time, so two quick taps cannot
// reach the server in the wrong order.
import { useState } from "react";
import { api } from "@/api/client";
import { type Theme, useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

const CHOICES: { value: Theme; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const SAVE_ERROR = "Could not save. Please try again.";

export function AppearanceSettings() {
  const { theme, setTheme } = useTheme();
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  async function choose(next: Theme) {
    // One save at a time. We ignore the pick instead of disabling the radios: a disabled
    // radio loses keyboard focus, and the arrow keys would stop working.
    if (saving) return;
    const old = theme;
    setFailed(false);
    setTheme(next); // show it now
    setSaving(true);
    try {
      const { response } = await api.PUT("/api/v1/me/theme", { body: { theme: next } });
      if (!response.ok) throw new Error("not saved");
    } catch {
      setTheme(old); // the server did not save it: show the saved one again
      setFailed(true);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex w-full max-w-md flex-col gap-2">
      {/* aria-busy tells screen readers a save is running. */}
      <fieldset aria-busy={saving || undefined} className="flex flex-col gap-1">
        <legend className="mb-2 text-sm font-medium">Theme</legend>
        {CHOICES.map(({ value, label }) => (
          // min-h-11 = 44px: a tap target big enough for a thumb. The whole row is the label.
          <label
            key={value}
            className={cn(
              "flex min-h-11 items-center gap-3 rounded-md border bg-card px-4 text-sm",
              saving ? "cursor-wait" : "cursor-pointer",
            )}
          >
            <input
              type="radio"
              name="theme"
              value={value}
              checked={theme === value}
              onChange={() => void choose(value)}
              className="size-4 accent-brand"
            />
            {label}
          </label>
        ))}
      </fieldset>
      {failed && (
        <p role="alert" className="text-sm text-destructive">
          {SAVE_ERROR}
        </p>
      )}
    </div>
  );
}
