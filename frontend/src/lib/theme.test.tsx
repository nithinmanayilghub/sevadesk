// Tests for applyTheme: the one place that writes data-theme on <html>.
import { beforeEach, expect, test } from "vitest";
import { applyTheme } from "./theme";

beforeEach(() => {
  delete document.documentElement.dataset.theme;
});

test("dark and light are written to <html data-theme>", () => {
  applyTheme("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  applyTheme("light");
  expect(document.documentElement.dataset.theme).toBe("light");
});

test("system removes data-theme, so the device decides", () => {
  applyTheme("dark");
  applyTheme("system");
  expect(document.documentElement.dataset.theme).toBeUndefined();
});

test("null (leaving /app) removes data-theme", () => {
  applyTheme("dark");
  applyTheme(null);
  expect(document.documentElement.dataset.theme).toBeUndefined();
});
