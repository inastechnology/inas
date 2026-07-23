import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
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

const errors = [];
const results = [];

async function openPage({
  path,
  viewport,
  screenshot,
  fullPage = false,
  mobileMenu = false,
  searchQuery = "",
  searchExpectedText = "WTR 潅水デバイス",
  requiredSelectors = [],
  requiredText = [],
}) {
  const page = await browser.newPage();
  page.on("pageerror", (error) => errors.push(`${path}: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`${path}: ${message.text()}`);
  });
  await page.evaluateOnNewDocument(() => localStorage.setItem("starlight-theme", "light"));
  await page.setCacheEnabled(false);
  await page.setViewport(viewport);
  const response = await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle0" });
  assert.equal(response?.status(), 200, `${path} must return HTTP 200`);
  assert(await page.$("h1"), `${path} must have one visible h1`);
  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(dimensions.scrollWidth <= dimensions.clientWidth + 1, `${path} overflows horizontally: ${JSON.stringify(dimensions)}`);
  assert.equal(await page.$eval('html', (element) => element.lang), "ja");
  assert(await page.$('button[data-open-modal]'), `${path} must expose site search`);
  for (const selector of requiredSelectors) {
    assert(await page.$(selector), `${path} must contain ${selector}`);
  }
  if (requiredText.length > 0) {
    const bodyText = await page.$eval("body", (element) => element.textContent || "");
    for (const text of requiredText) {
      assert(bodyText.includes(text), `${path} must contain ${text}`);
    }
  }

  if (searchQuery) {
    await page.waitForSelector('button[data-open-modal]:not([disabled])');
    await page.click('button[data-open-modal]');
    await page.type('.pagefind-ui__search-input', searchQuery);
    await page.waitForFunction(() => document.querySelectorAll('.pagefind-ui__result').length > 0);
    const searchText = await page.$eval('dialog', (element) => element.textContent || '');
    assert(
      searchText.includes(searchExpectedText),
      `search for ${searchQuery} must find ${searchExpectedText}`,
    );
    await page.keyboard.press('Escape');
  }

  if (mobileMenu) {
    const button = await page.$('button[aria-label="メニュー"]');
    assert(button, "mobile navigation button must exist");
    await page.click('starlight-menu-button button');
    await page.waitForFunction(() => document.querySelector('starlight-menu-button')?.getAttribute('aria-expanded') === 'true');
    assert.equal(await page.$eval("starlight-menu-button", (element) => element.getAttribute("aria-expanded")), "true");
  }

  const screenshotPath = join(artifactDir, screenshot);
  await page.screenshot({ path: screenshotPath, fullPage });
  results.push({ path, screenshot: screenshotPath, dimensions });
  await page.close();
}

try {
  await openPage({
    path: "/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-home-desktop.png",
    fullPage: true,
    searchQuery: "起動時潅水",
  });
  await openPage({
    path: "/devices/wtr/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-wtr-desktop.png",
    fullPage: true,
  });
  await openPage({
    path: "/start/overview/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-architecture-desktop.png",
    fullPage: true,
    requiredSelectors: [".system-architecture", ".architecture-hub", ".architecture-device"],
    requiredText: ["Raspberry Piで常時実行", "現行デバイスのmDNS"],
  });
  await openPage({
    path: "/start/hardware/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-hardware-desktop.png",
    fullPage: true,
    requiredText: ["最低目安 — 評価・小規模", "正式な保証スペックは検討中です"],
    searchQuery: "Raspberry Pi 5",
    searchExpectedText: "機器を選んで購入する",
  });
  await openPage({
    path: "/start/provided-hardware/",
    viewport: { width: 1280, height: 900, deviceScaleFactor: 1 },
    screenshot: "docs-provided-hardware-desktop.png",
    requiredText: ["準備中", "予定している利用開始フロー"],
  });
  await openPage({
    path: "/troubleshoot/watering/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-watering-troubleshoot-desktop.png",
  });
  await openPage({
    path: "/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-home-mobile.png",
  });
  await openPage({
    path: "/devices/wtr/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-wtr-mobile.png",
    mobileMenu: true,
  });
  await openPage({
    path: "/start/overview/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-architecture-mobile.png",
    fullPage: true,
    requiredSelectors: [".system-architecture"],
  });

  const index = await fetch(`${baseUrl}/sitemap-index.xml`).then((response) => response.text());
  const sitemapPaths = [...index.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname);
  assert(sitemapPaths.length > 0, "sitemap index must contain a sitemap");
  const documentXml = await fetch(`${baseUrl}${sitemapPaths[0]}`).then((response) => response.text());
  const pagePaths = [...documentXml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => new URL(match[1]).pathname);
  assert(pagePaths.length >= 29, `expected at least 29 public pages, found ${pagePaths.length}`);
  const failures = [];
  const internalLinks = new Set();
  for (const path of pagePaths) {
    const response = await fetch(`${baseUrl}${path}`);
    if (!response.ok) {
      failures.push({ path, status: response.status });
      continue;
    }
    const html = await response.text();
    for (const match of html.matchAll(/<a\b[^>]*\bhref=["']([^"']+)["']/gi)) {
      const target = new URL(match[1], `${baseUrl}${path}`);
      if (target.origin === new URL(baseUrl).origin) internalLinks.add(target.pathname);
    }
  }
  for (const path of internalLinks) {
    const response = await fetch(`${baseUrl}${path}`);
    if (!response.ok) failures.push({ path, status: response.status, source: "internal-link" });
  }
  assert.deepEqual(failures, [], `sitemap pages must be reachable: ${JSON.stringify(failures)}`);
  assert.deepEqual(errors, [], `browser console errors: ${JSON.stringify(errors)}`);

  const report = { baseUrl, pageCount: pagePaths.length, results };
  await writeFile(join(artifactDir, "smoke-report.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
} finally {
  await browser.close();
}
