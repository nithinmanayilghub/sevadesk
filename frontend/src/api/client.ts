// Typed API client. Relative URLs: the browser calls the same origin (Caddy routes /api to FastAPI).
import createClient from "openapi-fetch";
import { shouldRedirectToLogin } from "@/lib/auth";
import { goTo } from "@/lib/navigate";
import type { paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });

// One place for "session gone": any 401 sends the User to /login (story 2.2).
// schemaPath is the route as written in the schema, e.g. "/api/v1/me".
api.use({
  onResponse({ response, schemaPath }) {
    if (typeof window !== "undefined" && shouldRedirectToLogin(response.status, schemaPath, window.location.pathname)) {
      goTo("/login");
    }
  },
});
