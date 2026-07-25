import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const artifactDir = join(root, "artifacts");
const baseUrl = (process.env.DOCS_URL || "http://127.0.0.1:4321").replace(/\/$/, "");
await mkdir(artifactDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

async function inspectNetworkPage(viewport, screenshotName) {
  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => localStorage.setItem("starlight-theme", "light"));
  await page.setViewport(viewport);
  await page.setCacheEnabled(false);
  const response = await page.goto(`${baseUrl}/start/network/`, { waitUntil: "networkidle0" });
  assert.equal(response?.status(), 200);

  const selectors = [
    ".manual-prep-panel",
    ".manual-note--caution",
    ".manual-note--trouble",
    ".manual-steps",
    '.manual-visual svg[aria-label*="farm-wifi-2G"]',
  ];
  for (const selector of selectors) {
    assert(await page.$(selector), `network page must contain ${selector}`);
  }
  assert.equal(await page.$$eval(".manual-step", (items) => items.length), 5);
  assert.equal(await page.$$eval(".manual-visual", (items) => items.length), 10);

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(dimensions.scrollWidth <= dimensions.clientWidth + 1, JSON.stringify(dimensions));

  const urlBefore = page.url();
  await page.click(".concept-illustration > a");
  await page.waitForSelector("dialog.manual-lightbox[open]");
  assert.equal(page.url(), urlBefore, "lightbox must not navigate away from the page");
  assert(await page.$("dialog.manual-lightbox[open] img[src]"));
  await page.click(".manual-lightbox__close");
  await page.waitForSelector("dialog.manual-lightbox:not([open])");

  await page.screenshot({
    path: join(artifactDir, screenshotName),
    fullPage: true,
  });
  await page.close();
}

try {
  await inspectNetworkPage(
    { width: 1440, height: 1000, deviceScaleFactor: 1 },
    "docs-network-manual-desktop.png",
  );
  await inspectNetworkPage(
    { width: 390, height: 844, deviceScaleFactor: 1 },
    "docs-network-manual-mobile.png",
  );
  console.log("Manual visual smoke check passed.");
} finally {
  await browser.close();
}
