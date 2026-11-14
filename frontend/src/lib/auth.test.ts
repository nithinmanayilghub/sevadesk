// Tests for the log-in helpers: where a User lands (UX-DR18) and when a 401 sends them to /login.
import { expect, test } from "vitest";
import { landingPath, shouldRedirectToLogin } from "./auth";

test("Owner and Staff land on the Dashboard", () => {
  expect(landingPath(["owner", "technician"])).toBe("/app");
  expect(landingPath(["staff"])).toBe("/app");
});

test("Technician-only Users land on the Calendar", () => {
  expect(landingPath(["technician"])).toBe("/app/calendar");
});

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
