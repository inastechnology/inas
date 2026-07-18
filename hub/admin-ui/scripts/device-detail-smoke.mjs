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
  assert(await page.$('.device-guide img[src$="/device-family.png"]'), "the device collection must share the field-view visual language");
  assert.equal(await page.$$('.nav a[href="/demo/mqtt-devices"]').then((items) => items.length), 0, "the demo must not compete in normal navigation");
  await page.screenshot({ path: "/tmp/ina-device-list.png", fullPage: true });
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
  assert.equal(await page.$$eval('a[href="/mqtt-devices"]', (links) => links.length), 1, "detail must expose one catalog return path");
  assert(await page.$(".location-path a"), "the irrigation device must link to its field placement");
  await assertSelectedTab("monitoring");
  const soilHistoryLink = '.metric-action[aria-label="現在の土壌水分の履歴を見る"]';
  assert.equal(
    await page.$eval(soilHistoryLink, (link) => link.getAttribute("href")),
    "/mqtt-devices/INADS-DEMO-WTR-001?tab=monitoring#soil-moisture-chart",
  );
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.click(soilHistoryLink),
  ]);
  await assertSelectedTab("monitoring");
  assert.equal(new URL(page.url()).hash, "#soil-moisture-chart", "the current value must open its exact history chart");
  assert(await page.$("#soil-moisture-chart"));
  await page.click('.tab-button[data-tab-key="overview"]');
  await assertSelectedTab("overview");
  assert.equal(await page.$eval("#tab-overview", (panel) => panel.hidden), false);
  assert.equal(await page.$$(".readiness-card").then((items) => items.length), 4, "overview must make operational readiness scannable");
  assert.equal(
    await page.$eval('.metric-action[aria-label="次の潅水の設定を変更"]', (link) => link.getAttribute("href")),
    "/mqtt-devices/INADS-DEMO-WTR-001?tab=settings#watering-schedules",
  );
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
  assert(await page.$("#output-connection-map"), "watering settings must visualize the current equipment connections");
  assert.equal(await page.$$("#output-connection-map .switch-output").then((items) => items.length), 2);
  assert.equal(await page.$$(".setup-journey .setup-step").then((items) => items.length), 3, "watering setup must expose a three-step journey");
  assert.equal(await page.$eval('.setup-step[href="#output-connections"]', (link) => link.textContent?.includes("設備をつなぐ")), true);
  await page.screenshot({ path: "/tmp/ina-device-wtr-settings.png", fullPage: true });
  await page.click("#open-output-settings");
  assert.equal(await page.$eval("#output-settings-dialog", (dialog) => dialog.open), true);
  assert.equal(await page.$$("#output-settings-dialog .output-edit-row").then((items) => items.length), 2, "WTR must expose only its two supported ports");
  assert.equal(await page.$$("#output-settings-dialog [data-equipment-type]").then((items) => items.length), 8, "each port must offer illustrated equipment choices");
  const outputDialogText = await page.$eval("#output-settings-dialog", (dialog) => dialog.innerText || "");
  assert.match(outputDialogText, /水やりルートを組み立てる/);
  assert.match(outputDialogText, /ポンプ|バルブ|点滴チューブ|スプリンクラー/);
  assert.doesNotMatch(outputDialogText, /内部ID|接続端子|系統番号|MOSFET|mask/);
  const firstBuilderLane = "#output-settings-dialog .output-edit-row:first-child";
  await page.$eval(`${firstBuilderLane} [data-mosfet-enabled]`, (input) => input.click());
  assert.equal(await page.$eval(firstBuilderLane, (lane) => lane.classList.contains("disconnected")), true, "disabled ports must visibly disconnect their wire");
  assert.equal(await page.$eval(`${firstBuilderLane} [data-equipment-type="pump"]`, (card) => card.disabled), true, "equipment cards must rest while disconnected");
  await page.$eval(`${firstBuilderLane} [data-mosfet-enabled]`, (input) => input.click());
  assert.equal(await page.$eval(firstBuilderLane, (lane) => lane.classList.contains("connected")), true, "enabled ports must draw their wire immediately");
  await page.click(`${firstBuilderLane} [data-equipment-type="sprinkler"]`);
  assert.equal(await page.$eval(`${firstBuilderLane} [data-equipment-type="sprinkler"]`, (card) => card.getAttribute("aria-pressed")), "true");
  assert(await page.$(`${firstBuilderLane} [data-equipment-preview] svg`), "type selection must update the route preview icon");
  const firstSprinklerTarget = `${firstBuilderLane} [data-equipment-target]:not([data-equipment-target=""])`;
  assert(await page.$(firstSprinklerTarget), "the selected type must reveal matching destination cards");
  await page.click(firstSprinklerTarget);
  assert.notEqual(await page.$eval(`${firstBuilderLane} [data-mosfet-load]`, (input) => input.value), "");
  await page.screenshot({ path: "/tmp/ina-device-builder-dialog.png" });
  await page.click("[data-cancel-output-dialog]");
  assert.equal(await page.$eval('#runtime-config-form button[type="submit"]', (button) => button.disabled), true, "cancelled connection edits must keep the form pristine");
  await page.click("#open-output-settings");
  await page.click(`${firstBuilderLane} [data-equipment-type="sprinkler"]`);
  await page.click(`${firstBuilderLane} [data-equipment-target]:not([data-equipment-target=""])`);
  await page.click("[data-apply-output-dialog]");
  assert.equal(await page.$eval('#runtime-config-form button[type="submit"]', (button) => button.disabled), false, "applied route edits must make the setup saveable");
  assert(await page.$("#output-connection-map .switch-output-icon svg"), "the current route must retain an illustrated endpoint");
  const routePreview = await page.$eval("#runtime-config-json", (textarea) => JSON.parse(textarea.value));
  assert.match(routePreview.mosfet_switches[0].notes, /デモ用/, "legacy notes must survive visual editing");
  assert.match(routePreview.mosfet_switches[0].notes, /equipment_type=sprinkler/, "the selected picture must fit the existing notes schema");
  assert.equal("equipment_type" in routePreview.mosfet_switches[0], false, "the saved device schema must not gain a new field");
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const wateringSettingsOverflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(wateringSettingsOverflow <= 1, `mobile watering setup must not overflow horizontally: ${wateringSettingsOverflow}px`);
  await page.screenshot({ path: "/tmp/ina-device-wtr-settings-mobile.png", fullPage: true });
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await page.click("#open-soil-calibration-guide");
  assert.equal(await page.$eval("#soil-calibration-guide", (dialog) => dialog.open), true);
  assert.match(await page.$eval("#soil-calibration-guide", (dialog) => dialog.innerText || ""), /乾いた基準を記録する/);
  assert.match(await page.$eval("#soil-calibration-guide", (dialog) => dialog.innerText || ""), /湿った基準を記録する/);
  await page.screenshot({ path: "/tmp/ina-device-calibration-guide.png" });
  await page.click('#soil-calibration-guide [data-close-calibration-guide]');
  assert.match(await page.$eval("#watering-schedules", (section) => section.innerText || ""), /水を送る接続先/);
  assert.doesNotMatch(await page.$eval("#watering-schedules", (section) => section.innerText || ""), /ON 秒数|mask|MOSFET/);
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
  assert(await page.$("#firmware-dropzone"), "firmware registration must start with a drag-and-drop target");
  assert(await page.$('img[src$="/firmware-care.png"]'), "firmware flow must include its visual guide");
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
  assert.match(environmentSettingsText, /つないだセンサー/);
  assert.doesNotMatch(environmentSettingsText, /MOSFET SW 管理|潅水予約|分割潅水/);
  assert.doesNotMatch(environmentSettingsText, /センサー番号|読み取り方式|読み取り位置|読み取り開始位置/);
  assert.equal(await page.$eval('[data-env-sensor-panel="par"]', (panel) => panel.hidden), false, "the enabled light sensor must reveal its own controls");
  assert.equal(await page.$eval('[data-env-sensor-panel="soil"]', (panel) => panel.hidden), true, "an unused soil sensor must hide its settings");
  assert.equal(await page.$eval('[data-env-sensor-panel="soil"]', (panel) => getComputedStyle(panel).display), "none", "the OFF sensor body must be visually absent, not merely marked hidden");
  assert.equal(await page.$eval('[data-env-sensor-advanced="soil"]', (panel) => panel.hidden), true, "unused soil maintenance values must also stay hidden");
  assert.equal(await page.$eval("#env-calibration-dialog", (dialog) => dialog.open), false, "the tuning dialog must open only when requested");
  await page.$eval("#env-soil-enabled", (input) => input.click());
  assert.equal(await page.$eval('[data-env-sensor-panel="soil"]', (panel) => panel.hidden), false, "enabling the soil sensor must reveal only its card body");
  assert.equal(await page.$eval('[data-env-calibration-summary="soil_ph"]', (summary) => summary.textContent), "未調整");
  await page.click('[data-env-tune-target="soil_ph"]');
  assert.equal(await page.$eval("#env-calibration-dialog", (dialog) => dialog.open), true, "display adjustment must happen in a modal");
  assert.equal(await page.$eval("#env-calibration-reference-value", (range) => range.max), "14");
  assert.equal(await page.$eval("#env-calibration-reference-value", (range) => range.step), "0.1");
  assert.equal(await page.$eval("#env-calibration-unit", (unit) => unit.textContent), "pH");
  await page.$eval("#env-calibration-reference-value", (range) => {
    range.value = "6.5";
    range.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(await page.$eval("#env-calibration-reference-display", (output) => output.textContent), "6.5");
  await page.screenshot({ path: "/tmp/ina-device-env-sensor-workbench.png", fullPage: true });
  await page.click('[data-env-calibration-action="capture_reference"]');
  assert.equal(await page.$eval("#env-calibration-dialog", (dialog) => dialog.open), false, "recording a reference must return to the equipment view");
  assert.equal(await page.$eval('[data-env-calibration-summary="soil_ph"]', (summary) => summary.textContent), "基準 6.5 pH", "the recorded value must be visible on its adjustment button");
  assert.equal(await page.$eval('#runtime-config-form button[type="submit"]', (button) => button.disabled), false, "a recorded reference must be saveable");
  const sensorConfigPreview = await page.$eval("#runtime-config-json", (textarea) => JSON.parse(textarea.value));
  assert.equal(sensorConfigPreview.env_sensors.par.enabled, true, "the existing light sensor setting must be preserved");
  assert.equal(sensorConfigPreview.env_sensors.soil.enabled, true, "the newly connected soil sensor must be reflected in the existing schema");
  assert.equal(sensorConfigPreview.env_calibration.target, "soil_ph");
  assert.equal(sensorConfigPreview.env_calibration.mode, "capture_reference");
  assert.equal(sensorConfigPreview.env_calibration.reference_value, 6.5);
  await page.evaluate((config) => window.renderRuntimeConfigForm(config), sensorConfigPreview);
  assert.equal(await page.$eval('[data-env-calibration-summary="soil_ph"]', (summary) => summary.textContent), "基準 6.5 pH", "the recorded value must survive rendering saved configuration");
  await page.screenshot({ path: "/tmp/ina-device-env-calibration-summary.png", fullPage: true });

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
      "/tmp/ina-device-list.png",
      "/tmp/ina-device-wtr-overview.png",
      "/tmp/ina-device-wtr-settings.png",
      "/tmp/ina-device-builder-dialog.png",
      "/tmp/ina-device-wtr-settings-mobile.png",
      "/tmp/ina-device-calibration-guide.png",
      "/tmp/ina-device-wtr-firmware.png",
      "/tmp/ina-device-pending-diagnostics.png",
      "/tmp/ina-device-env-monitoring.png",
      "/tmp/ina-device-env-sensor-workbench.png",
      "/tmp/ina-device-env-calibration-summary.png",
      "/tmp/ina-device-env-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
