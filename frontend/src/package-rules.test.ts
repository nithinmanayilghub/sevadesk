// Guards for the frontend setup (AR-3): one typed API client, no other data-fetching library,
// and the shadcn/ui components are in place.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

// Vitest runs from the frontend folder, where package.json lives.
const pkg = JSON.parse(readFileSync(resolve(process.cwd(), "package.json"), "utf8"));
const allDeps = { ...pkg.dependencies, ...pkg.devDependencies };

const FORBIDDEN = ["swr", "@tanstack/react-query", "react-query", "axios", "ky", "@apollo/client", "urql"];

test("no data-fetching library is installed", () => {
  for (const name of FORBIDDEN) {
    expect(allDeps, `${name} must not be installed`).not.toHaveProperty(name);
  }
  expect(pkg.dependencies).toHaveProperty("openapi-fetch");
});

test("every dependency is pinned to an exact version", () => {
  for (const [name, version] of Object.entries(pkg.dependencies as Record<string, string>)) {
    expect(version, `${name} must be pinned`).toMatch(/^\d/);
  }
});

test("ui components exist", async () => {
  const { Button } = await import("@/components/ui/button");
  const { Input } = await import("@/components/ui/input");
  const { Label } = await import("@/components/ui/label");
  expect([Button, Input, Label].every(Boolean)).toBe(true);
});
