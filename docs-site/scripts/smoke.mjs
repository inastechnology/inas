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
const generalSetupForbiddenText = [
  "mDNS",
  "MQTT",
  "DHCP",
  "SSID",
  "VLAN",
  "hostname",
  "Mosquitto",
  "Runtime Config",
  "Cloudflare Access",
  "Cloudflare Tunnel",
  "OTA",
  "予約IP",
];

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
  forbiddenText = [],
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
  if (requiredText.length > 0 || forbiddenText.length > 0) {
    const bodyText = await page.$eval("body", (element) => element.textContent || "");
    for (const text of requiredText) {
      assert(bodyText.includes(text), `${path} must contain ${text}`);
    }
    for (const text of forbiddenText) {
      assert(!bodyText.includes(text), `${path} must not expose advanced term ${text}`);
    }
  }

  const documentedImageSelector = ".product-screenshot img, .concept-illustration img";
  const documentedImageCount = await page.$$eval(documentedImageSelector, (images) => images.length);
  if (documentedImageCount > 0) {
    await page.$$eval(documentedImageSelector, (images) => {
      for (const image of images) image.loading = "eager";
    });
    await page.waitForFunction(
      (selector) => [...document.querySelectorAll(selector)]
        .every((image) => image.complete && image.naturalWidth > 0),
      { timeout: 10_000 },
      documentedImageSelector,
    );
  }

  if (searchQuery) {
    await page.waitForSelector('button[data-open-modal]:not([disabled])');
    await page.click('button[data-open-modal]');
    await page.type('.pagefind-ui__search-input', searchQuery);
    await page.waitForFunction(
      (expectedText) => document.querySelector('dialog')?.textContent?.includes(expectedText),
      { timeout: 10_000 },
      searchExpectedText,
    );
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
    requiredSelectors: [".manifesto-preview"],
    requiredText: ["ここまで読み進めたあなたへ", "自動化は、いばらの道です"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/why-inas/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-why-inas-desktop.png",
    fullPage: true,
    searchQuery: "いばらの道",
    searchExpectedText: "INASを使う人へ",
    requiredSelectors: [
      ".manifesto-page-lead",
      ".manifesto-statement",
      'img[src="/images/illustrations/why-inas-explorer.webp"]',
      'img[src="/images/illustrations/why-inas-real-work.webp"]',
      'img[src="/images/illustrations/why-inas-field-listening.webp"]',
      'img[src="/images/illustrations/why-inas-next-generation.webp"]',
      'img[src="/images/illustrations/why-inas-open-tools.webp"]',
    ],
    requiredText: ["未来の農を一緒につくる仲間", "子どもたちの時代にも、食糧をつくり続ける", "私たちが約束すること"],
  });
  await openPage({
    path: "/devices/wtr/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-wtr-desktop.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/illustrations/wtr-hardware.webp"]',
      'img[src="/images/screenshots/device-first-setup.webp"]',
    ],
  });
  await openPage({
    path: "/start/overview/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-overview-desktop.png",
    fullPage: true,
    requiredSelectors: [".process-map.process-map--three"],
    requiredText: ["INASを形づくる3つのもの", "通常利用では、難しい設定は不要です"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/choose-path/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-choose-path-desktop.png",
    fullPage: true,
    requiredSelectors: [".route-options"],
    requiredText: ["一般の利用者はこちらを選びます", "現在利用可能・技術者向け"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/hardware/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-hardware-desktop.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/illustrations/hardware-overview.webp"]',
      ".manual-visual",
    ],
    requiredText: ["最低目安 — 評価・小規模", "正式な保証スペックは検討中です"],
    searchQuery: "Raspberry Pi 5",
    searchExpectedText: "機器を選んで購入する",
  });
  await openPage({
    path: "/start/prerequisites/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-prerequisites-desktop.png",
    requiredSelectors: [
      'img[src="/images/illustrations/site-readiness.webp"]',
      ".manual-visual",
    ],
  });
  await openPage({
    path: "/start/network/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-network-desktop.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/illustrations/network-layout.webp"]',
      ".manual-prep-panel",
      ".manual-steps",
      ".manual-note--caution",
      ".manual-note--trouble",
    ],
    requiredText: ["Wi-Fiルーターや家電の初期設定と同じ考え方です", "来客用Wi-Fiは使いません"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/safety/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-safety-desktop.png",
    requiredSelectors: [
      ".safety-story",
      'img[src="/images/illustrations/safety-story-dry-hub.webp"]',
      'img[src="/images/illustrations/safety-story-manual-stop.webp"]',
      'img[src="/images/illustrations/safety-story-short-test.webp"]',
      'img[src="/images/illustrations/safety-story-emergency-stop.webp"]',
      'img[src="/images/illustrations/electrical-water-safety.webp"]',
      ".manual-prep-panel",
      ".manual-steps",
      ".manual-note--safe",
    ],
    requiredText: ["機器を開けたり、配線を変えたりしません", "最初の潅水を安全に試す手順"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/devices/wrs/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-wrs-desktop.png",
    requiredSelectors: [
      'img[src="/images/illustrations/wrs-hardware.webp"]',
      'svg[aria-label*="1本のバス"]',
    ],
  });
  await openPage({
    path: "/devices/sensors/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-sensors-desktop.png",
    requiredSelectors: [
      'img[src="/images/illustrations/sensor-hardware.webp"]',
      'svg[aria-label*="土壌水分プローブ"]',
      'svg[aria-label*="12V電源"]',
    ],
  });
  await openPage({
    path: "/start/provided-hardware/",
    viewport: { width: 1280, height: 900, deviceScaleFactor: 1 },
    screenshot: "docs-provided-hardware-desktop.png",
    fullPage: true,
    requiredSelectors: [".setup-flyer", ".setup-flyer__steps", 'img[src="/images/screenshots/device-catalog.webp"]'],
    requiredText: ["準備中", "箱を開けたら、1台ずつつなぐだけ", "機器一覧に表示されたら完了"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/technical/architecture/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-technical-architecture-desktop.png",
    fullPage: true,
    requiredSelectors: [".system-architecture", ".architecture-hub", ".architecture-device", ".communication-routes", ".system-components"],
    requiredText: ["現行デバイスのmDNS", "Mosquitto", "管理画面とAPIを外部から閲覧・操作するためだけ"],
  });
  await openPage({
    path: "/technical/networking/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-technical-networking-desktop.png",
    fullPage: true,
    requiredSelectors: ['img[src="/images/illustrations/network-layout.webp"]'],
    requiredText: ["技術スタック", "現行デバイスでDHCP予約IPを使う理由", "セキュリティ境界"],
  });
  await openPage({
    path: "/technical/hardware-safety/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-technical-hardware-safety-desktop.png",
    requiredSelectors: ['img[src="/images/illustrations/electrical-water-safety.webp"]'],
    requiredText: ["技術者向け・通電前に確認", "受入試験"],
  });
  await openPage({
    path: "/start/quickstart/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-quickstart-flow-desktop.png",
    requiredSelectors: [".manual-prep-panel", ".manual-steps"],
  });
  await openPage({
    path: "/hub/raspberry-pi/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-raspberry-pi-manual-desktop.png",
    fullPage: true,
    requiredSelectors: [".manual-prep-panel", ".manual-steps"],
    requiredText: ["作業前に用意するもの", "2つの画面で送受信を試す"],
  });
  await openPage({
    path: "/hub/install/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-hub-install-manual-desktop.png",
    fullPage: true,
    requiredSelectors: [".manual-prep-panel", ".manual-steps"],
    requiredText: ["開始前にそろえる情報", "再起動後も画面を開けるか確かめる"],
  });
  await openPage({
    path: "/hub/cloudflare/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-cloudflare-manual-desktop.png",
    fullPage: true,
    requiredSelectors: [
      ".manual-prep-panel",
      ".manual-steps",
      'svg[aria-label*="OK・NG比較図"]',
    ],
    requiredText: ["公開前に確認すること", "許可と拒否を両方試す"],
  });
  await openPage({
    path: "/hub/update-backup/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-update-backup-manual-desktop.png",
    fullPage: true,
    requiredSelectors: [".manual-prep-panel", ".manual-steps"],
    requiredText: ["戻せる状態を作ってから更新します", "画面と機器が元の状態へ戻ったか確認する"],
  });
  await openPage({
    path: "/configure/fields-devices/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-field-hierarchy-desktop.png",
    requiredSelectors: [".hierarchy-map", ".manual-prep-panel", ".manual-steps", ".connection-guide", 'img[src="/images/screenshots/device-catalog.webp"]'],
    requiredText: ["機器番号を入力して「登録」する必要はありません", "機器一覧に新しい機器が表示されれば、接続成功です"],
  });
  await openPage({
    path: "/configure/watering/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-watering-flow-desktop.png",
    requiredSelectors: [".process-map", ".manual-prep-panel", ".manual-steps", 'svg[aria-label*="朝6時30分"]', 'svg[aria-label*="分割潅水"]', 'svg[aria-label*="土の水分が基準"]'],
  });
  await openPage({
    path: "/configure/settings/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-settings-guide-desktop.png",
    fullPage: true,
    requiredSelectors: [
      ".settings-scope-map",
      ".setting-explain-list",
      'img[src="/images/screenshots/user-preferences.webp"]',
      'img[src="/images/screenshots/watering-settings.webp"]',
    ],
    requiredText: ["個人設定", "機器の「動作設定」", "管理者だけが変更する設定"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/technical/app-settings/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-app-settings-technical-desktop.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/screenshots/app-settings-ai.webp"]',
      'img[src="/images/screenshots/app-settings-notifications.webp"]',
      'img[src="/images/screenshots/app-settings-instagram.webp"]',
      'img[src="/images/screenshots/app-settings-system.webp"]',
    ],
    requiredText: ["管理者・技術担当者向け", "秘密値は保存後に再表示せず"],
  });
  await openPage({
    path: "/devices/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-device-build-flow-desktop.png",
    fullPage: true,
    requiredSelectors: [".process-map"],
  });
  await openPage({
    path: "/operate/firmware/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-firmware-flow-desktop.png",
    requiredSelectors: [".process-map"],
  });
  await openPage({
    path: "/troubleshoot/device-offline/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-offline-flow-desktop.png",
    requiredSelectors: [
      'img[src="/images/screenshots/device-diagnostics.webp"]',
      'img[src="/images/screenshots/device-wifi-recovery.webp"]',
    ],
    requiredText: ["Hubが最後に確認", "確認する理由", "一般ユーザーが通信トピックやサーバーのログを確認する必要はありません"],
  });
  await openPage({
    path: "/troubleshoot/config/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-config-flow-desktop.png",
    requiredSelectors: ['img[src="/images/screenshots/watering-operation-check.webp"]'],
    requiredText: ["設定の受信", "確認する理由"],
  });
  await openPage({
    path: "/reference/runtime-config/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-runtime-config-flow-desktop.png",
    requiredSelectors: [".process-map"],
  });
  await openPage({
    path: "/community/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-community-flow-desktop.png",
    fullPage: true,
    requiredSelectors: [".process-map"],
  });
  await openPage({
    path: "/troubleshoot/watering/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-watering-troubleshoot-desktop.png",
    requiredSelectors: ['img[src="/images/screenshots/watering-operation-check.webp"]'],
    requiredText: ["画面で確認する内容と理由", "動作確認", "通電中の配線作業はしない"],
  });
  await openPage({
    path: "/operate/ai-calendar/",
    viewport: { width: 1440, height: 1000, deviceScaleFactor: 1 },
    screenshot: "docs-ai-calendar-desktop.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/screenshots/ai-cultivation-plan.webp"]',
      'img[src="/images/screenshots/ai-proposal-review.webp"]',
    ],
    requiredText: ["現在の計画と変更案を比較する", "AI提案は作業判断の材料です"],
  });
  await openPage({
    path: "/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-home-mobile.png",
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/devices/wtr/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-wtr-mobile.png",
    mobileMenu: true,
    requiredSelectors: ['img[src="/images/illustrations/wtr-hardware.webp"]'],
  });
  await openPage({
    path: "/start/hardware/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-hardware-mobile.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/illustrations/hardware-overview.webp"]',
      ".manual-visual",
    ],
  });
  await openPage({
    path: "/operate/ai-calendar/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-ai-calendar-mobile.png",
    requiredSelectors: [
      'img[src="/images/screenshots/ai-cultivation-plan.webp"]',
      'img[src="/images/screenshots/ai-proposal-review.webp"]',
    ],
  });
  await openPage({
    path: "/start/why-inas/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-why-inas-mobile.png",
    fullPage: true,
    requiredSelectors: [
      ".manifesto-page-lead",
      ".manifesto-statement",
      'img[src="/images/illustrations/why-inas-explorer.webp"]',
      'img[src="/images/illustrations/why-inas-real-work.webp"]',
      'img[src="/images/illustrations/why-inas-field-listening.webp"]',
      'img[src="/images/illustrations/why-inas-next-generation.webp"]',
      'img[src="/images/illustrations/why-inas-open-tools.webp"]',
    ],
  });
  await openPage({
    path: "/start/overview/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-overview-mobile.png",
    fullPage: true,
    requiredSelectors: [".process-map.process-map--three"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/network/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-network-mobile.png",
    fullPage: true,
    requiredSelectors: [
      'img[src="/images/illustrations/network-layout.webp"]',
      ".manual-prep-panel",
      ".manual-steps",
      ".manual-note--caution",
    ],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/safety/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-safety-manual-mobile.png",
    fullPage: true,
    requiredSelectors: [".safety-story", ".safety-story__grid", ".manual-prep-panel", ".manual-steps", ".manual-note--safe"],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/start/provided-hardware/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-provided-hardware-mobile.png",
    fullPage: true,
    requiredSelectors: [".setup-flyer", ".setup-flyer__steps", 'img[src="/images/screenshots/device-catalog.webp"]'],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/configure/settings/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-settings-guide-mobile.png",
    fullPage: true,
    requiredSelectors: [".settings-scope-map", ".setting-explain-list", 'img[src="/images/screenshots/user-preferences.webp"]'],
    forbiddenText: generalSetupForbiddenText,
  });
  await openPage({
    path: "/hub/install/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-hub-install-manual-mobile.png",
    fullPage: true,
    requiredSelectors: [".manual-prep-panel", ".manual-steps"],
  });
  await openPage({
    path: "/technical/networking/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-technical-networking-mobile.png",
    fullPage: true,
    requiredSelectors: ['img[src="/images/illustrations/network-layout.webp"]'],
    requiredText: ["技術スタック", "障害調査の順序"],
  });
  await openPage({
    path: "/configure/watering/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-watering-flow-mobile.png",
    fullPage: true,
    requiredSelectors: [".process-map", ".manual-prep-panel", ".manual-steps"],
  });
  await openPage({
    path: "/configure/fields-devices/",
    viewport: { width: 390, height: 844, deviceScaleFactor: 1 },
    screenshot: "docs-field-hierarchy-mobile.png",
    fullPage: true,
    requiredSelectors: [".hierarchy-map", ".manual-prep-panel", ".manual-steps", ".connection-guide"],
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
