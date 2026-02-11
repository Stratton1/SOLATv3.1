import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { chromium } from "playwright";

const ROUTES = [
  { name: "status", path: "/" },
  { name: "terminal", path: "/terminal" },
  { name: "backtests", path: "/backtests" },
  { name: "optimise", path: "/optimise" },
  { name: "library", path: "/library" },
  { name: "blotter", path: "/blotter" },
  { name: "settings", path: "/settings" },
];

const EXPLICIT_BASE_URL = process.argv[2] ?? process.env.SCREENSHOT_BASE_URL ?? null;
const BASE_URL_CANDIDATES = [
  "http://127.0.0.1:1420",
  "http://localhost:1420",
];
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const outputDir = path.resolve(process.cwd(), "screenshots", timestamp);

async function isReachable(url) {
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(2000),
    });
    return response.ok || response.status < 500;
  } catch {
    return false;
  }
}

async function resolveBaseUrl() {
  if (EXPLICIT_BASE_URL) {
    return EXPLICIT_BASE_URL;
  }

  for (const candidate of BASE_URL_CANDIDATES) {
    if (await isReachable(candidate)) {
      return candidate;
    }
  }

  throw new Error(
    "Frontend dev server is not reachable. Start UI with `pnpm dev:ui` first.",
  );
}

async function waitForAppReady(page) {
  // If the splash screen gets stuck due to engine state, skip into app.
  const skipButton = page.getByRole("button", { name: "Skip to App" });
  if (await skipButton.isVisible().catch(() => false)) {
    await skipButton.click();
  }

  await page.waitForSelector(".app", { timeout: 30_000 });
  await page.waitForTimeout(750);
}

async function captureRoutes() {
  const baseUrl = await resolveBaseUrl();
  await mkdir(outputDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();

  try {
    console.log(`Using frontend base URL: ${baseUrl}`);
    for (const route of ROUTES) {
      const url = new URL(route.path, baseUrl).toString();
      await page.goto(url, { waitUntil: "networkidle", timeout: 60_000 });
      await waitForAppReady(page);
      await page.screenshot({
        path: path.join(outputDir, `${route.name}.png`),
        fullPage: true,
      });
      console.log(`Captured ${route.path} -> ${route.name}.png`);
    }
  } finally {
    await context.close();
    await browser.close();
  }
}

captureRoutes()
  .then(() => {
    console.log(`Screenshots saved to: ${outputDir}`);
  })
  .catch((error) => {
    console.error("Failed to capture screenshots.");
    console.error(error);
    process.exitCode = 1;
  });
