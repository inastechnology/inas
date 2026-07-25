import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const docsRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const repositoryRoot = path.dirname(docsRoot);
const hubRoot = path.join(repositoryRoot, "hub");
const adminUiRoot = path.join(hubRoot, "admin-ui");
const outputDir = path.join(docsRoot, "public", "images", "screenshots");
const artifactDir = path.join(docsRoot, "artifacts");
const fixtureDate = process.env.DOCS_SCREENSHOT_DATE || "2026-07-24";
const sensitiveSentinel = "PRODUCTION_SECRET_MUST_NOT_ENTER_DOCS_DEMO";

const captures = [
  {
    name: "device-first-setup.webp",
    path: "/docs-demo/device-setup?reason=unconfigured",
    ready: "form",
    expectedText: ["INA Water Controller Setup", "Connection settings are not configured yet.", "MQTT Broker"],
    viewport: { width: 720, height: 980, deviceScaleFactor: 1 },
    fullPage: true,
  },
  {
    name: "device-wifi-recovery.webp",
    path: "/docs-demo/device-setup?reason=wifi_failure&populated=1",
    ready: "form",
    expectedText: ["Wi-Fi connection failed before reaching the MQTT broker.", "INAS-Demo-2G", "192.0.2.10"],
    viewport: { width: 720, height: 980, deviceScaleFactor: 1 },
    fullPage: true,
  },
  {
    name: "field-catalog.webp",
    path: "/fields",
    ready: ".field-list",
    expectedText: ["圃場一覧", "イチゴ実証圃場", "長野県"],
  },
  {
    name: "field-installation-layout.webp",
    path: "/fields/demo-strawberry-field/layout?space=space-demo-greenhouse-1",
    ready: ".installation-app",
    expectedText: ["イチゴ実証圃場", "イチゴ畝A", "点滴潅水コントローラー"],
  },
  {
    name: "device-catalog.webp",
    path: "/mqtt-devices",
    ready: ".device-grid",
    expectedText: ["機器一覧", "デモ潅水機1", "ハウス環境センサー"],
  },
  {
    name: "user-preferences.webp",
    path: "/preferences",
    ready: "#preference-form",
    expectedText: ["個人設定", "タイムゾーン", "文字の大きさ", "栽培アドバイスの詳しさ"],
  },
  {
    name: "app-settings-ai.webp",
    path: "/settings?section=ai",
    ready: "#ai-settings-form",
    scrollTo: "#ai",
    expectedText: ["アプリ設定", "AI機能", "テキスト・栽培計画", "画像解析"],
  },
  {
    name: "app-settings-notifications.webp",
    path: "/settings?section=notifications",
    ready: "#notification-settings-form",
    scrollTo: "#notifications",
    expectedText: ["通知", "すべてのDiscord通知", "今日の栽培作業", "機器の確認"],
  },
  {
    name: "app-settings-instagram.webp",
    path: "/settings?section=instagram",
    ready: "#instagram",
    scrollTo: "#instagram",
    expectedText: ["Instagram", "投稿処理開始時刻", "投稿元カメラ", "投稿アカウント"],
  },
  {
    name: "app-settings-system.webp",
    path: "/settings?section=system",
    ready: "#system",
    scrollTo: "#system",
    expectedText: ["システム", "接続設定", "初期設定・再設定", "追加機能"],
  },
  {
    name: "watering-operation-check.webp",
    path: "/mqtt-devices/INADS-DEMO-WTR-001",
    ready: ".priority-panel",
    expectedText: ["現在の潅水判断", "動作確認", "設定を受信"],
  },
  {
    name: "watering-settings.webp",
    path: "/mqtt-devices/INADS-DEMO-WTR-001?tab=settings",
    ready: "#runtime-config-form",
    scrollTo: "#tab-config",
    expectedText: ["動作設定", "灌水予約", "保存して機器へ反映"],
  },
  {
    name: "field-daily-dashboard.webp",
    path: "/fields/demo-strawberry-field",
    ready: "#field-status-dashboard",
    expectedText: ["イチゴ実証圃場", "取得中の環境値", "作業TODO"],
  },
  {
    name: "field-work-board.webp",
    path: "/fields/demo-strawberry-field/calendar?view=work",
    ready: ".calendar-kanban",
    scrollTo: ".calendar-kanban",
    expectedText: ["圃場の作業", "未完了", "作業中", "完了・見送り"],
  },
  {
    name: "ai-cultivation-plan.webp",
    path: "/fields/demo-strawberry-field/calendar?view=crop",
    ready: ".calendar-generation",
    expectedText: ["作物別の栽培計画", "AI栽培計画を作り直す", "培地の施肥と残存肥効"],
  },
  {
    name: "ai-proposal-review.webp",
    path: "/fields/demo-strawberry-field/calendar?view=crop&review=ai",
    ready: ".regeneration-review-dialog",
    expectedText: ["現在の栽培カレンダー", "AIの提案", "取り入れない"],
  },
  {
    name: "firmware-update.webp",
    path: "/mqtt-devices/INADS-DEMO-WTR-001?tab=firmware",
    ready: "#ota-target",
    scrollTo: "#tab-firmware",
    expectedText: ["機器ソフトウェアの更新", "現在のバージョン", "更新予約"],
  },
  {
    name: "device-diagnostics.webp",
    path: "/mqtt-devices/INADS-DEMO-WTR-003?tab=maintenance",
    ready: "#tab-maintenance .panel",
    scrollTo: ".detail-tabs",
    click: "#connection-help > summary",
    expectedText: ["保守・管理", "困ったとき：通信を確認する", "Hubが最後に確認"],
  },
];

function buildAdminUi() {
  const result = spawnSync("npm", ["run", "build"], {
    cwd: adminUiRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (result.status === 0) return;
  throw new Error(`Hub admin UI build failed.\n${result.stdout || ""}\n${result.stderr || ""}`);
}

async function availablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

async function waitForDemo(baseUrl, child, serverLog) {
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`Documentation demo exited before it was ready.\n${serverLog.join("")}`);
    }
    try {
      const response = await fetch(`${baseUrl}/docs-demo`);
      if (response.ok) return;
    } catch {
      // The child is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Documentation demo did not become ready.\n${serverLog.join("")}`);
}

async function stopChild(child) {
  if (child.exitCode !== null) return;
  const closed = new Promise((resolve) => child.once("close", resolve));
  child.kill("SIGTERM");
  await Promise.race([closed, new Promise((resolve) => setTimeout(resolve, 3000))]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function capturePage(browser, baseUrl, spec) {
  const page = await browser.newPage();
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setViewport(spec.viewport || { width: 1440, height: 960, deviceScaleFactor: 1 });
  await page.setCacheEnabled(false);
  const response = await page.goto(`${baseUrl}${spec.path}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
  assert.equal(response?.status(), 200, `${spec.path} must return HTTP 200`);
  await page.waitForSelector(spec.ready, { visible: true, timeout: 30_000 });
  await new Promise((resolve) => setTimeout(resolve, 450));

  const text = await page.$eval("body", (element) => element.textContent || "");
  const searchablePage = `${text}\n${await page.content()}`;
  for (const expected of spec.expectedText) {
    assert(searchablePage.includes(expected), `${spec.path} must contain ${expected}`);
  }
  assert(!searchablePage.includes(sensitiveSentinel), `${spec.path} exposed an inherited environment sentinel`);

  const dimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(
    dimensions.scrollWidth <= dimensions.clientWidth + 1,
    `${spec.path} overflows horizontally: ${JSON.stringify(dimensions)}`,
  );

  if (spec.scrollTo) {
    await page.$eval(spec.scrollTo, (element) => element.scrollIntoView({ block: "start" }));
    await new Promise((resolve) => setTimeout(resolve, 250));
  } else {
    await page.evaluate(() => window.scrollTo(0, 0));
  }

  if (spec.click) {
    await page.click(spec.click);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }

  const captureDimensions = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(
    captureDimensions.scrollWidth <= captureDimensions.clientWidth + 1,
    `${spec.path} overflows horizontally after preparing the screenshot: ${JSON.stringify(captureDimensions)}`,
  );

  const outputPath = path.join(outputDir, spec.name);
  await page.screenshot({
    path: outputPath,
    type: "webp",
    quality: 90,
    fullPage: Boolean(spec.fullPage),
  });
  await page.close();
  assert.deepEqual(errors, [], `${spec.path} browser errors: ${JSON.stringify(errors)}`);
  return {
    name: spec.name,
    source: spec.path,
    readySelector: spec.ready,
    width: spec.viewport?.width || 1440,
    height: spec.viewport?.height || 960,
  };
}

buildAdminUi();
await mkdir(outputDir, { recursive: true });
await mkdir(artifactDir, { recursive: true });
const temporaryRoot = await mkdtemp(path.join(os.tmpdir(), "inas-docs-demo-"));
const port = await availablePort();
const baseUrl = `http://127.0.0.1:${port}`;
const serverLog = [];
const server = spawn("uv", ["run", "python", "scripts/run_admin_demo_server.py"], {
  cwd: hubRoot,
  env: {
    ...process.env,
    HUB_DEMO_HOST: "127.0.0.1",
    HUB_DEMO_PORT: String(port),
    HUB_DEMO_WORK_DIR: path.join(temporaryRoot, "work"),
    HUB_DEMO_LOCAL_STORAGE_BASE_DIR: path.join(temporaryRoot, "storage"),
    HUB_DEMO_SCENARIO: "documentation",
    HUB_DEMO_TODAY: fixtureDate,
    TURSO_DATABASE_URL: `libsql://${sensitiveSentinel}`,
    TURSO_AUTH_TOKEN: sensitiveSentinel,
    S3_ENDPOINT_URL: `https://${sensitiveSentinel}.invalid`,
    S3_ACCESS_KEY: sensitiveSentinel,
    S3_SECRET_KEY: sensitiveSentinel,
    MQTT_BROKER_URL: `${sensitiveSentinel}.invalid`,
    MQTT_BROKER_USERNAME: sensitiveSentinel,
    MQTT_BROKER_PASSWORD: sensitiveSentinel,
    AI_ENABLED: "true",
    AI_TEXT_ANALYZE_API_KEY: sensitiveSentinel,
    DISCORD_ENABLED: "true",
    DISCORD_WEBHOOK_URL: `https://${sensitiveSentinel}.invalid`,
    INSTAGRAM_ACCESS_TOKEN: sensitiveSentinel,
    INSTAGRAM_ADMIN_USERNAME: sensitiveSentinel,
    SWITCHBOT_BASE_URL: `https://${sensitiveSentinel}.invalid`,
    HUB_BACKUP_DIR: path.join(temporaryRoot, sensitiveSentinel),
    DEVICE_CONFIG_DEFAULT_NTP_SERVER: `${sensitiveSentinel}.internal`,
    WEATHER_LATITUDE: sensitiveSentinel,
    WEATHER_LONGITUDE: sensitiveSentinel,
    WEATHER_FORECAST_URL: `https://${sensitiveSentinel}.invalid`,
    INSTAGRAM_WEATHER_FORECAST_URL: `https://${sensitiveSentinel}.invalid`,
    CLOUDFLARE_ACCESS_ALLOWED_EMAILS: `${sensitiveSentinel}@example.invalid`,
    CLOUDFLARE_TUNNEL_HOSTNAME: `${sensitiveSentinel}.invalid`,
    SENSOR_SAVE_IMAGE: "true",
    PYTHONUNBUFFERED: "1",
  },
  stdio: ["ignore", "pipe", "pipe"],
});
server.stdout.on("data", (chunk) => serverLog.push(chunk.toString()));
server.stderr.on("data", (chunk) => serverLog.push(chunk.toString()));

let browser;
try {
  await waitForDemo(baseUrl, server, serverLog);
  browser = await puppeteer.launch({
    executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
    headless: true,
    args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
  });
  const results = [];
  for (const spec of captures) results.push(await capturePage(browser, baseUrl, spec));
  const report = {
    generatedAt: new Date().toISOString(),
    fixtureDate,
    demoBaseUrl: baseUrl,
    isolation: {
      workDirectory: path.join(temporaryRoot, "work"),
      storageDirectory: path.join(temporaryRoot, "storage"),
      productionEnvironmentSentinelRejected: true,
    },
    captures: results,
  };
  await writeFile(path.join(artifactDir, "product-screenshot-report.json"), `${JSON.stringify(report, null, 2)}\n`);
  process.stdout.write(`Captured ${results.length} documentation screenshots in ${outputDir}\n`);
} finally {
  if (browser) await browser.close();
  await stopChild(server);
  await rm(temporaryRoot, { recursive: true, force: true });
}
