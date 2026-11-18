"use client";
// The User's chosen theme (story 2.6): System, Light or Dark. The /app layout asks GET /api/v1/me,
// writes the answer on <html data-theme="...">, and shares it here so a page can show and change it.
// No data-theme means "System": the CSS then follows the device.
import { createContext, useContext, type ReactNode } from "react";
import type { components } from "@/api/schema";

export type Theme = components["schemas"]["Theme"];

// Writes (or removes) data-theme on <html>. null = leaving /app, so public pages follow the device.
export function applyTheme(theme: Theme | null): void {
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
  else delete document.documentElement.dataset.theme;
}

type ThemeValue = { theme: Theme; setTheme: (theme: Theme) => void };

// The default (no provider) is "system" and a setter that does nothing.
const ThemeContext = createContext<ThemeValue>({ theme: "system", setTheme: () => {} });

export function ThemeProvider({ theme, setTheme, children }: ThemeValue & { children: ReactNode }) {
  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
