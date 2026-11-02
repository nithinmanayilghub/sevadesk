// Typed API client. Relative URLs: the browser calls the same origin (Caddy routes /api to FastAPI).
import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const api = createClient<paths>({ baseUrl: "" });
