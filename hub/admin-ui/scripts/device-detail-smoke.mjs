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
  await page.goto(`${baseUrl}/mqtt-devices`, { waitUntil: "networkidle0" });
  assert(await page.$("#device-list-search"), "the device collection must provide a search field");
  const deviceCount = await page.$$("#device-list-grid .device-tile").then((items) => items.length);
  assert(deviceCount > 1, "the demo must expose multiple devices for filtering");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.type("#device-list-search", "WTR-003"),
  ]);
  assert.equal(new URL(page.url()).searchParams.get("q"), "WTR-003");
  assert.equal(await page.$$eval("#device-list-grid .device-tile", (tiles) => tiles.length), 1);
  assert.match(await page.$eval("#device-result-summary", (summary) => summary.textContent || ""), /1件中 1件/);

  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-WTR-001?tab=monitoring`, { waitUntil: "networkidle0" });
  assert.equal(await page.$$eval(".tab-button", (tabs) => tabs.length), 5);
  const wateringDecisionText = await page.$eval(".priority-panel", (panel) => panel.innerText || "");
  assert.match(wateringDecisionText, /次の潅水/);
  assert.match(wateringDecisionText, /土壌水分しきい値/);
  assert.match(wateringDecisionText, /現在の土壌水分/);
  assert.equal(await page.$$eval("h2", (headings) => headings.filter((heading) => heading.textContent?.trim() === "設置ビュー").length), 0);
  assert(await page.$(".location-path a"), "the irrigation device must link to its field placement");
  await assertSelectedTab("monitoring");
  await page.click('.tab-button[data-tab-key="overview"]');
  await assertSelectedTab("overview");
  assert.equal(await page.$eval("#tab-overview", (panel) => panel.hidden), false);
  await page.screenshot({ path: "/tmp/ina-device-wtr-overview.png", fullPage: true });
  await page.click('.tab-button[data-tab-key="monitoring"]');
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
  assert.equal(await page.$eval('#metadata-form button[type="submit"]', (button) => button.disabled), true, "unchanged metadata must not be saved again");
  assert.equal(await page.$eval('#runtime-config-form button[type="submit"]', (button) => button.disabled), true, "unchanged runtime config must not be saved again");
  assert.equal(await page.$eval("#save-push-runtime-config", (button) => button.disabled), true, "unchanged runtime config must not be sent");
  await page.$eval("#ntp-server", (input) => {
    input.value = `${input.value}-edited`;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(await page.$eval('#runtime-config-form button[type="submit"]', (button) => button.disabled), false, "changed runtime config must be saveable");
  assert.equal(await page.$eval("#save-push-runtime-config", (button) => button.disabled), false, "changed config on an active device must be saveable and sendable");

  await page.click('.tab-button[data-tab-key="diagnostics"]');
  await assertSelectedTab("diagnostics");
  assert(await page.$('[data-state-action="disable"]'));
  assert.equal(await page.$('[data-state-action="approve"]'), null, "an active device must not offer approval");
  assert.equal(await page.$('[data-state-action="retire"]'), null, "an active device must be stopped before retirement");

  await page.click('.tab-button[data-tab-key="firmware"]');
  await assertSelectedTab("firmware");
  assert.equal(await page.$eval("#tab-firmware", (panel) => panel.hidden), false);
  assert(await page.$("#firmware-target-form"));
  assert(await page.$("#target-firmware-version + .static-searchable-select"), "firmware target must use the shared searchable dropdown");
  assert.equal(await page.$eval("#target-firmware-version + .static-searchable-select input[type=\"search\"]", (input) => input.offsetParent === null), true, "firmware search must stay hidden inside the closed dropdown");
  await page.click("#target-firmware-version + .static-searchable-select .searchable-select-control");
  await page.waitForSelector("#target-firmware-version + .static-searchable-select input[type=\"search\"]", { visible: true });
  await page.keyboard.press("Escape");
  assert(await page.$("#firmware-upload-form"));
  await page.screenshot({ path: "/tmp/ina-device-wtr-firmware.png", fullPage: true });

  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-WTR-003?tab=diagnostics`, { waitUntil: "networkidle0" });
  await assertSelectedTab("diagnostics");
  assert(await page.$('[data-state-action="approve"]'));
  assert(await page.$('[data-state-action="retire"]'));
  assert.equal(await page.$('[data-state-action="disable"]'), null, "a pending device cannot be stopped before approval");
  await page.screenshot({ path: "/tmp/ina-device-pending-diagnostics.png", fullPage: true });
  await page.click('.tab-button[data-tab-key="settings"]');
  assert.equal(await page.$eval("#save-push-runtime-config", (button) => button.disabled), true, "a pending device cannot receive runtime config");
  assert.match(await page.$eval("#device-push-disabled", (notice) => notice.textContent || ""), /承認待ち/);

  await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-ENV-001?tab=monitoring`, { waitUntil: "networkidle0" });
  await assertSelectedTab("monitoring");
  await waitForCharts(3);
  const envText = await page.$eval("body", (body) => body.textContent || "");
  assert.match(envText, /環境センサー/);
  assert.match(envText, /24\.6 ℃/);
  assert.match(envText, /68\.0 %/);
  assert(await page.$(".location-path a"), "the sensor must link to its field placement");
  const environmentLocation = await page.$eval(".detail-header .lead", (lead) => lead.textContent || "");
  assert.doesNotMatch(environmentLocation, /未設置/);
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
    layoutAssignmentLinks: true,
    wateringDecisionFirst: true,
    mobileOverflow: overflow,
    screenshots: [
      "/tmp/ina-device-wtr-monitoring.png",
      "/tmp/ina-device-wtr-overview.png",
      "/tmp/ina-device-wtr-firmware.png",
      "/tmp/ina-device-pending-diagnostics.png",
      "/tmp/ina-device-env-monitoring.png",
      "/tmp/ina-device-env-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
