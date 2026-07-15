import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

async function waitForCharts(count) {
  await page.waitForFunction(
    (expected) => document.querySelectorAll(".chart-body .js-plotly-plot").length >= expected,
    { timeout: 15_000 },
    count,
  );
}

async function assertSelectedTab(key) {
  assert.equal(
    await page.$eval(`.tab-button[data-tab-key="${key}"]`, (tab) => tab.getAttribute("aria-selected")),
    "true",
  );
}

try {
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-WTR-001?tab=monitoring`, { waitUntil: "networkidle0" });
  assert.equal(await page.$$eval(".tab-button", (tabs) => tabs.length), 5);
  await assertSelectedTab("monitoring");
  await waitForCharts(2);
  assert.equal(await page.$$eval(".chart-settings-link", (links) => links.length), 2);
  assert.equal(
    await page.$eval(".chart-settings-link", (link) => link.getAttribute("href")),
    "/mqtt-devices/INADS-DEMO-WTR-001?tab=settings",
  );
  await page.screenshot({ path: "/tmp/ina-device-wtr-monitoring.png", fullPage: true });

  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.click(".chart-settings-link"),
  ]);
  await assertSelectedTab("settings");
  assert.equal(await page.$eval("#tab-config", (panel) => panel.hidden), false);
  assert(await page.$("#metadata-form"));

  await page.click('.tab-button[data-tab-key="firmware"]');
  await assertSelectedTab("firmware");
  assert.equal(await page.$eval("#tab-firmware", (panel) => panel.hidden), false);
  assert(await page.$("#firmware-target-form"));
  assert(await page.$("#firmware-upload-form"));
  await page.screenshot({ path: "/tmp/ina-device-wtr-firmware.png", fullPage: true });

  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-ENV-001?tab=monitoring`, { waitUntil: "networkidle0" });
  await assertSelectedTab("monitoring");
  await waitForCharts(3);
  const envText = await page.$eval("body", (body) => body.textContent || "");
  assert.match(envText, /環境センサー/);
  assert.match(envText, /24\.6 ℃/);
  assert.match(envText, /68\.0 %/);
  assert.equal(await page.$$eval('[data-chart-kind="watering"]', (charts) => charts.length), 0);
  assert.equal(await page.$$eval(".chart-settings-link", (links) => links.length), 3);
  await page.screenshot({ path: "/tmp/ina-device-env-monitoring.png", fullPage: true });

  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-ENV-001?tab=settings`, { waitUntil: "networkidle0" });
  await assertSelectedTab("settings");
  const environmentSettingsText = await page.$eval("#tab-config", (panel) => panel.innerText || "");
  assert.match(environmentSettingsText, /環境センサー 校正/);
  assert.doesNotMatch(environmentSettingsText, /MOSFET SW 管理|潅水予約|分割潅水/);

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `mobile page must not overflow horizontally: ${overflow}px`);
  await page.screenshot({ path: "/tmp/ina-device-env-mobile.png", fullPage: true });

  await page.goto(`${baseUrl}/fields/demo-strawberry-field`, { waitUntil: "networkidle0" });
  await page.click('[data-field-tab="monitoring"]');
  assert(await page.$('.scope-device-settings[href$="?tab=settings"]'));
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));

  process.stdout.write(JSON.stringify({
    deviceTabs: 5,
    wtrCharts: 2,
    environmentCharts: 3,
    settingsDeepLink: true,
    firmwareTab: true,
    mobileOverflow: overflow,
    screenshots: [
      "/tmp/ina-device-wtr-monitoring.png",
      "/tmp/ina-device-wtr-firmware.png",
      "/tmp/ina-device-env-monitoring.png",
      "/tmp/ina-device-env-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
