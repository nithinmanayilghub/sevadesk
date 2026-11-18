// Tests for next.config.ts (story 2.5): the invite page holds a secret token in its address.
import { expect, test } from "vitest";
import nextConfig from "../next.config";

test("invite pages send Referrer-Policy: no-referrer, so the token never leaves in a Referer header", async () => {
  const rules = (await nextConfig.headers?.()) ?? [];
  const invite = rules.find((rule) => rule.source === "/invite/:path*");
  expect(invite?.headers).toContainEqual({ key: "Referrer-Policy", value: "no-referrer" });
});
