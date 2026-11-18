// Tests for the log-in helper: when a 401 sends the User to /login.
// (Where a User lands after log-in is tested in lib/pages.test.ts.)
import { expect, test } from "vitest";
import { shouldRedirectToLogin } from "./auth";

test("a 401 from any other call sends the User to /login", () => {
  expect(shouldRedirectToLogin(401, "/api/v1/me", "/app")).toBe(true);
});

test("a wrong password on the log-in call itself does not redirect", () => {
  expect(shouldRedirectToLogin(401, "/api/v1/login", "/login")).toBe(false);
  expect(shouldRedirectToLogin(401, "/api/v1/login", "/app")).toBe(false);
});

test("other statuses and the /login page itself do not redirect", () => {
  expect(shouldRedirectToLogin(403, "/api/v1/me", "/app")).toBe(false);
  expect(shouldRedirectToLogin(401, "/api/v1/me", "/login")).toBe(false);
});
