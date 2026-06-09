#!/usr/bin/env node
import { mkdir, readFile, stat } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(SCRIPT_DIR, "..");
const DEFAULT_CONFIG = join(SCRIPT_DIR, "map_capture_views.json");
const DEFAULT_OUT_DIR = join(REPO_ROOT, "output", "playwright", "map-captures");
const DEFAULT_PORT = 5182;

function readArgs(argv) {
  const options = {
    config: DEFAULT_CONFIG,
    outDir: DEFAULT_OUT_DIR,
    baseUrl: null,
    port: DEFAULT_PORT,
    headed: false,
    keepServer: false,
    timeoutMs: 90000,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    const next = argv[index + 1];
    if (arg === "--config" && next) {
      options.config = resolve(next);
      index += 1;
    } else if (arg === "--out" && next) {
      options.outDir = resolve(next);
      index += 1;
    } else if (arg === "--url" && next) {
      options.baseUrl = next.replace(/\/$/, "");
      index += 1;
    } else if (arg === "--port" && next) {
      options.port = Number(next);
      index += 1;
    } else if (arg === "--headed") {
      options.headed = true;
    } else if (arg === "--keep-server") {
      options.keepServer = true;
    } else if (arg === "--timeout-ms" && next) {
      options.timeoutMs = Number(next);
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (!Number.isFinite(options.port)) throw new Error("--port must be a number");
  if (!Number.isFinite(options.timeoutMs)) throw new Error("--timeout-ms must be a number");
  return options;
}

function printHelp() {
  console.log(`Capture deterministic map screenshots.

Usage:
  pnpm capture:maps
  pnpm capture:maps -- --config scripts/map_capture_views.json --out output/playwright/map-captures
  pnpm capture:maps -- --url http://127.0.0.1:5181

Options:
  --config <path>       JSON view list. Default: scripts/map_capture_views.json
  --out <dir>           Screenshot output directory. Default: output/playwright/map-captures
  --url <base-url>      Reuse an already-running app instead of starting Vite
  --port <number>       Port for the temporary Vite server. Default: 5182
  --headed              Show the browser while capturing
  --keep-server         Leave the temporary Vite server running
  --timeout-ms <number> Per-view timeout. Default: 90000
`);
}

async function loadConfig(configPath) {
  const text = await readFile(configPath, "utf8");
  const config = JSON.parse(text);
  if (!Array.isArray(config.views) || config.views.length === 0) {
    throw new Error(`${configPath} must contain a non-empty "views" array`);
  }
  return config;
}

function mergeView(defaults, view) {
  return {
    ...defaults,
    ...view,
    viewport: {
      ...(defaults.viewport ?? {}),
      ...(view.viewport ?? {}),
    },
    overlays: {
      ...(defaults.overlays ?? {}),
      ...(view.overlays ?? {}),
    },
    query: {
      ...(defaults.query ?? {}),
      ...(view.query ?? {}),
    },
  };
}

function appendNumber(params, name, value) {
  if (value == null) return;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error(`${name} must be a finite number`);
  }
  params.set(name, String(value));
}

function appendBoolean(params, name, value) {
  if (value == null) return;
  params.set(name, value ? "1" : "0");
}

function urlForView(baseUrl, view) {
  if (!view.id || typeof view.id !== "string") throw new Error("Every view needs a string id");
  const url = new URL(baseUrl);
  const params = url.searchParams;
  params.set("capture", "1");
  if (view.view) params.set("view", view.view);
  if (view.slice) params.set("slice", view.slice);
  if (view.detail) params.set("detail", view.detail);
  if (view.texture) params.set("texture", view.texture);
  if (view.smoothing) params.set("smoothing", view.smoothing);
  if (view.scene) params.set("scene", view.scene);
  if (view.sourceMode) params.set("sourceMode", view.sourceMode);
  if (view.sourceId) params.set("sourceId", view.sourceId);
  appendNumber(params, "water", view.water);
  appendNumber(params, "years", view.years);
  appendNumber(params, "longitude", view.viewState?.longitude);
  appendNumber(params, "latitude", view.viewState?.latitude);
  appendNumber(params, "zoom", view.viewState?.zoom);
  appendNumber(params, "pitch", view.viewState?.pitch);
  appendNumber(params, "bearing", view.viewState?.bearing);

  for (const [name, value] of Object.entries(view.overlays ?? {})) {
    appendBoolean(params, name, Boolean(value));
  }
  for (const [name, value] of Object.entries(view.query ?? {})) {
    params.set(name, String(value));
  }
  return url.toString();
}

async function waitForServer(baseUrl, timeoutMs) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(baseUrl);
      if (response.ok) return;
    } catch {
      // The server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Server did not become ready: ${baseUrl}`);
}

async function startVite(port) {
  const viteBin = join(REPO_ROOT, "node_modules", ".bin", "vite");
  const child = spawn(viteBin, ["--host", "127.0.0.1", "--port", String(port)], {
    cwd: REPO_ROOT,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.on("data", (chunk) => process.stdout.write(`[vite] ${chunk}`));
  child.stderr.on("data", (chunk) => process.stderr.write(`[vite] ${chunk}`));
  child.on("exit", (code) => {
    if (code !== 0 && code !== null) process.stderr.write(`[vite] exited with code ${code}\n`);
  });
  return child;
}

async function captureView(page, view, baseUrl, outDir, timeoutMs) {
  const url = urlForView(baseUrl, view);
  const width = Number(view.viewport?.width ?? 1440);
  const height = Number(view.viewport?.height ?? 1200);
  if (!Number.isFinite(width) || !Number.isFinite(height)) {
    throw new Error(`${view.id}: viewport width and height must be numbers`);
  }

  await page.setViewportSize({ width, height });
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  await page.waitForSelector('main[data-capture-ready="true"]', { timeout: timeoutMs });
  await page.waitForLoadState("networkidle", { timeout: timeoutMs }).catch(() => undefined);
  await page.waitForTimeout(Number(view.waitAfterReadyMs ?? 1500));

  const canvasState = await page.evaluate(() =>
    Array.from(document.querySelectorAll("canvas")).map((canvas) => ({
      width: canvas.width,
      height: canvas.height,
    })),
  );
  const screenshotPath = join(outDir, `${view.id}.png`);
  await page.screenshot({ path: screenshotPath, fullPage: false });
  const screenshotStats = await stat(screenshotPath);
  return {
    id: view.id,
    url,
    screenshotPath,
    bytes: screenshotStats.size,
    viewport: { width, height },
    canvasState,
  };
}

async function main() {
  const options = readArgs(process.argv.slice(2));
  const config = await loadConfig(options.config);
  await mkdir(options.outDir, { recursive: true });

  const baseUrl = options.baseUrl ?? `http://127.0.0.1:${options.port}`;
  let server = null;
  if (!options.baseUrl) {
    server = await startVite(options.port);
    await waitForServer(baseUrl, 30000);
  }

  const browser = await chromium.launch({ headless: !options.headed });
  const page = await browser.newPage({ deviceScaleFactor: 1 });
  const results = [];

  try {
    for (const rawView of config.views) {
      const view = mergeView(config.defaults ?? {}, rawView);
      process.stdout.write(`Capturing ${view.id}...\n`);
      results.push(await captureView(page, view, baseUrl, options.outDir, options.timeoutMs));
    }
  } finally {
    await browser.close();
    if (server && !options.keepServer) {
      server.kill("SIGTERM");
    }
  }

  console.log(JSON.stringify({
    config: options.config,
    outDir: options.outDir,
    captured: results,
  }, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
});
