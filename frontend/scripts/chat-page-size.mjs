// The Chat Page size check (NFR-6): the first load of /c/{slug} must be at most 200 KB gzip.
// Customers open this page on cheap phones and slow mobile data, so every KB counts.
//
// How: start the production build (`next start`), fetch one Chat Page, find every file the
// browser must download for it (scripts, stylesheets, preloaded fonts), gzip each one, and
// add them up. Exit 1 if the total is over the limit, so CI fails.
//
// Run: npm run build && npm run check:chat-size
import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";
import { gzipSync } from "node:zlib";

export const LIMIT_BYTES = 204_800; // 200 KB
const PORT = 3999;
// Any slug works: an unknown one shows "Chat page not found", which loads the same files.
const PAGE_PATH = "/c/size-check";

// A path on our own server ("/_next/..."), not a full URL to another site ("//cdn...").
function isOwnPath(value) {
  return value.startsWith("/") && !value.startsWith("//");
}

function attribute(tag, name) {
  const match = tag.match(new RegExp(`\\s${name}=["']([^"']*)["']`, "i"));
  return match ? match[1] : null;
}

/** Every file the browser downloads at first load, from the page HTML. No duplicates. */
export function assetPaths(html) {
  const paths = new Set();
  for (const [tag] of html.matchAll(/<script\b[^>]*>/gi)) {
    // nomodule scripts are for very old browsers only: modern phones skip them.
    if (/\snomodule\b/i.test(tag)) continue;
    const src = attribute(tag, "src");
    if (src && isOwnPath(src)) paths.add(src);
  }
  for (const [tag] of html.matchAll(/<link\b[^>]*>/gi)) {
    const rel = (attribute(tag, "rel") ?? "").toLowerCase();
    const href = attribute(tag, "href");
    if ((rel === "stylesheet" || rel === "preload") && href && isOwnPath(href)) paths.add(href);
  }
  return [...paths];
}

/** The size in bytes after gzip: about what travels over the network. */
export function gzipBytes(data) {
  return gzipSync(data).length;
}

async function fetchBytes(url, fetchFn) {
  const response = await fetchFn(url);
  if (response.status !== 200) {
    throw new Error(`${new URL(url).pathname} answered ${response.status}, not 200`);
  }
  return new Uint8Array(await response.arrayBuffer());
}

/** Fetch the page and every file it loads. Returns the total and one row per file. */
export async function measure(baseUrl, fetchFn) {
  const page = await fetchBytes(`${baseUrl}${PAGE_PATH}`, fetchFn);
  const rows = [[PAGE_PATH, gzipBytes(page)]];
  for (const path of assetPaths(new TextDecoder().decode(page))) {
    rows.push([path, gzipBytes(await fetchBytes(`${baseUrl}${path}`, fetchFn))]);
  }
  const total = rows.reduce((sum, [, bytes]) => sum + bytes, 0);
  return { total, rows };
}

async function waitForServer(url, seconds) {
  for (let i = 0; i < seconds * 2; i++) {
    try {
      await fetch(url);
      return;
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 500)); // not up yet
    }
  }
  throw new Error(`the server did not start within ${seconds} s`);
}

async function main() {
  // No shell: start Node itself with Next's own start file. Works the same on Linux and Windows.
  const nextBin = createRequire(import.meta.url).resolve("next/dist/bin/next");
  const server = spawn(process.execPath, [nextBin, "start", "-p", String(PORT)], { stdio: "ignore" });
  const baseUrl = `http://localhost:${PORT}`;
  try {
    await waitForServer(`${baseUrl}${PAGE_PATH}`, 60);
    const { total, rows } = await measure(baseUrl, fetch);
    for (const [path, bytes] of rows) console.log(`${String(bytes).padStart(8)}  ${path}`);
    console.log(`${String(total).padStart(8)}  TOTAL (limit ${LIMIT_BYTES})`);
    if (total > LIMIT_BYTES) {
      console.error(`Chat Page first load is ${total} bytes gzip: over the ${LIMIT_BYTES} limit (NFR-6).`);
      process.exitCode = 1;
    }
  } finally {
    server.kill();
  }
}

// Run main() only when started as a script, not when a test imports this file.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
