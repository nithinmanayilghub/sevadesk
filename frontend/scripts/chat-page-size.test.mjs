// @vitest-environment node
// Tests for the Chat Page size check (NFR-6): which files count, and how they are summed.
import { expect, test } from "vitest";
import { assetPaths, gzipBytes, measure } from "./chat-page-size.mjs";

const HTML = `<!DOCTYPE html><html><head>
<link rel="stylesheet" href="/_next/static/css/app.css" data-precedence="next"/>
<link rel="preload" href="/_next/static/media/inter.woff2" as="font" type="font/woff2" crossorigin=""/>
<script src="/_next/static/chunks/main.js" async=""></script>
<script async="" src="/_next/static/chunks/page.js"></script>
<script src="/_next/static/chunks/main.js" async=""></script>
<script src="/_next/static/chunks/polyfills.js" noModule=""></script>
<script>self.__next_f.push([1,"inline"])</script>
<link rel="icon" href="/favicon.ico"/>
</head><body></body></html>`;

test("finds scripts, stylesheets and preloads", () => {
  expect(assetPaths(HTML).sort()).toEqual([
    "/_next/static/chunks/main.js",
    "/_next/static/chunks/page.js",
    "/_next/static/css/app.css",
    "/_next/static/media/inter.woff2",
  ]);
});

test("gzipBytes is smaller than the raw size for repeated text", () => {
  const text = "chat page ".repeat(1000);
  expect(gzipBytes(text)).toBeGreaterThan(0);
  expect(gzipBytes(text)).toBeLessThan(text.length);
});

// A fake server: each path answers with its own text, or 404 if it is not in the map.
function fakeFetch(files) {
  return async (url) => {
    const path = new URL(url).pathname;
    const body = files[path];
    return body === undefined ? new Response("missing", { status: 404 }) : new Response(body);
  };
}

const PAGE = `<script src="/a.js"></script><link rel="stylesheet" href="/b.css"/>`;

test("measure sums the page and its assets", async () => {
  const files = { "/c/size-check": PAGE, "/a.js": "console.log(1)", "/b.css": "body{}" };
  const { total, rows } = await measure("http://localhost:3999", fakeFetch(files));
  expect(rows.map(([path]) => path)).toEqual(["/c/size-check", "/a.js", "/b.css"]);
  expect(total).toBe(gzipBytes(PAGE) + gzipBytes("console.log(1)") + gzipBytes("body{}"));
});

test("measure counts preloads from the Link header too", async () => {
  // Next.js sends the font preload as an HTTP header, not as a <link> tag in the HTML.
  const font = "</_next/static/media/inter.woff2>; rel=preload; as=\"font\"; crossorigin=\"\"";
  const files = { "/c/size-check": "<p>hi</p>", "/_next/static/media/inter.woff2": "font bytes" };
  const fetchFn = async (url) => {
    const response = await fakeFetch(files)(url);
    if (new URL(url).pathname === "/c/size-check") response.headers.set("Link", font);
    return response;
  };
  const { rows } = await measure("http://localhost:3999", fetchFn);
  expect(rows.map(([path]) => path)).toEqual(["/c/size-check", "/_next/static/media/inter.woff2"]);
});

test("fails when an asset is missing", async () => {
  const files = { "/c/size-check": PAGE, "/a.js": "console.log(1)" };
  await expect(measure("http://localhost:3999", fakeFetch(files))).rejects.toThrow("/b.css");
});
