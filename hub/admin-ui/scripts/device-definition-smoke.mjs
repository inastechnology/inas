import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39311";
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

const devices = [
  ["WTR", "INADS-DEMO-WTR-001", ["ntp_server", "timezone_offset_sec", "moisture_threshold", "force_watering", "startup_watering_test", "debug_log_on_wake", "ota_check_interval_sec", "watering_pattern", "soil_calibration", "env_sensors", "env_calibration", "schedules"]],
  ["WRS", "INADS-DEMO-WRS-001", ["ntp_server", "timezone_offset_sec", "sleep_sec", "moisture_threshold", "force_watering", "debug_log_on_wake", "ota_check_interval_sec", "env_sensors", "wrs", "schedules"]],
  ["ENV", "INADS-DEMO-ENV-001", ["ntp_server", "timezone_offset_sec", "sleep_sec", "ota_check_interval_sec", "env_sensors", "env_calibration"]],
  ["SOI", "INADS-DEMO-SOI-001", ["ntp_server", "timezone_offset_sec", "sleep_sec", "ota_check_interval_sec", "soil_calibration"]],
  ["FGT", "INADS-DEMO-FGT-001", ["ntp_server", "timezone_offset_sec", "sleep_sec", "debug_log_on_wake", "ota_check_interval_sec", "fgt", "schedules"]],
];

try {
  await page.goto(`${baseUrl}/mqtt-devices`, { waitUntil: "networkidle0" });
  for (const [kind, deviceId] of devices) {
    assert(await page.$(`a[href="/mqtt-devices/${deviceId}"]`), `${kind} must be visible in the device catalog`);
  }
  await page.screenshot({ path: "/tmp/ina-device-definition-list.png", fullPage: true });

  for (const [kind, deviceId, expectedKeys] of devices) {
    const response = await page.goto(`${baseUrl}/mqtt-devices/${deviceId}?tab=settings`, { waitUntil: "networkidle0" });
    assert.equal(response.status(), 200, `${kind} settings must load`);
    assert.equal(await page.$eval('.tab-button[data-tab-key="settings"]', (tab) => tab.getAttribute("aria-selected")), "true");
    const definitionKind = await page.evaluate(() => deviceDefinition.device.kind);
    assert.equal(definitionKind, kind);
    const preview = await page.$eval("#runtime-config-json", (textarea) => JSON.parse(textarea.value));
    assert.deepEqual(Object.keys(preview).sort(), [...expectedKeys].sort(), `${kind} preview must be the exact outbound Runtime Config`);
    const payload = await page.evaluate(async (id) => {
      const response = await fetch(`/local/api/mqtt-devices/${encodeURIComponent(id)}/runtime-config/payload`);
      return response.json();
    }, deviceId);
    assert.deepEqual(Object.keys(payload).sort(), [...expectedKeys].sort(), `${kind} API payload must match its firmware definition`);
    assert.equal("mosfet_switches" in preview, false, `${kind} firmware payload must not contain Hub installation metadata`);

    if (kind === "FGT") {
      assert.equal(await page.$$("#fertigation-recipe .switch-output").then((items) => items.length), 5, "FGT must show its five fixed outputs");
      assert.equal(await page.$$("#fertigation-recipe [data-definition-path]").then((items) => items.length), 17, "FGT timed outputs must be editable with farmer-facing fields");
      assert.equal(await page.$('[data-definition-path="fgt.enabled"]'), null, "FGT scheduled operation must not expose an overall off switch");
      const flowText = await page.$eval("#fertigation-recipe", (section) => section.innerText);
      for (const label of ["水を入れる", "A液を量る", "B液を量る", "タンクを混ぜる", "植物へ送る"]) assert.match(flowText, new RegExp(label));
      assert.doesNotMatch(flowText, /MOSFET|mask|内部ID|modbus|端子/);
      assert.equal(preview.fgt.enabled, true);
      assert.equal(preview.fgt.timed_outputs.enabled, true);
      assert.deepEqual(preview.fgt.timed_outputs.nutrient_a, { on_sec: 120, off_sec: 0, repeat_count: 1 });
      assert.deepEqual(preview.fgt.timed_outputs.nutrient_b, { on_sec: 0, off_sec: 0, repeat_count: 0 });
      assert.equal(preview.sleep_sec, 3600);
      assert.doesNotMatch(flowText, /mL/);
      assert.match(await page.$eval("#scheduled-operation-inline-warning", (warning) => warning.innerText), /予約時刻に潅水されません/);
      assert.equal(await page.$$("#fertigation-recipe .switch-output.enabled").then((items) => items.length), 1);
      assert.equal(await page.$$("#fertigation-recipe .switch-output.disabled").then((items) => items.length), 4);
      await page.$eval("#save-runtime-json", (button) => button.click());
      await page.waitForSelector("#scheduled-operation-warning-dialog[open]");
      assert.match(await page.$eval("#scheduled-operation-warning-dialog", (dialog) => dialog.innerText), /潅水ポンプのON時間/);
      assert.equal(await page.$("#scheduled-operation-enable-before-save"), null, "FGT operation is always enabled and needs no checkbox");
      await page.click("[data-cancel-scheduled-operation-warning]");
    }
    await page.screenshot({ path: `/tmp/ina-device-definition-${kind.toLowerCase()}-settings.png`, fullPage: true });
    if (kind === "FGT") {
      await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
      await new Promise((resolve) => setTimeout(resolve, 250));
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      assert(overflow <= 1, `FGT timed-output settings must not overflow on mobile: ${overflow}px`);
      await page.screenshot({ path: "/tmp/ina-device-definition-fgt-settings-mobile.png", fullPage: true });
      await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    }

    await page.goto(`${baseUrl}/mqtt-devices/${deviceId}?tab=monitoring`, { waitUntil: "networkidle0" });
    assert.equal(await page.$eval('.tab-button[data-tab-key="monitoring"]', (tab) => tab.getAttribute("aria-selected")), "true");
    assert(await page.$(".metric-action"), `${kind} must expose a direct history action`);
    if (kind === "ENV") {
      const text = await page.$eval(".priority-panel", (panel) => panel.innerText);
      assert.match(text, /未接続/);
      assert.match(text, /920 µmol\/m²\/s/);
    }
    if (kind === "FGT") {
      const text = await page.$eval(".priority-panel", (panel) => panel.innerText);
      assert.match(text, /未取得/, "an enabled FGT sensor without a sample must remain visible as waiting");
    }
    await page.screenshot({ path: `/tmp/ina-device-definition-${kind.toLowerCase()}-monitoring.png`, fullPage: true });
  }

  assert.deepEqual(browserErrors, [], `browser errors: ${browserErrors.join(" | ")}`);
  console.log("Device Definition demo verified for WTR, WRS, ENV, SOI, and FGT.");
} finally {
  await browser.close();
}
