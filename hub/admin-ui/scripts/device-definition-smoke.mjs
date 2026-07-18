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
  ["WTR", "INADS-DEMO-WTR-001", ["ntp_server", "timezone_offset_sec", "moisture_threshold", "force_watering", "debug_log_on_wake", "ota_check_interval_sec", "watering_pattern", "soil_calibration", "env_sensors", "env_calibration", "schedules"]],
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
      assert.equal(await page.$$("#fertigation-recipe .switch-output").then((items) => items.length), 5, "FGT must show its five fixed farming steps");
      assert.equal(await page.$$("#fertigation-recipe [data-definition-path]").then((items) => items.length), 7, "FGT recipe must be editable with farmer-facing fields");
      const flowText = await page.$eval("#fertigation-recipe", (section) => section.innerText);
      for (const label of ["水を入れる", "A液を量る", "B液を量る", "タンクを混ぜる", "植物へ送る"]) assert.match(flowText, new RegExp(label));
      assert.doesNotMatch(flowText, /MOSFET|mask|内部ID|modbus|端子/);
      assert.equal(preview.fgt.enabled, false, "FGT must remain opt-in by default");
      assert.equal(preview.fgt.recipe.initial_water_ml, 1250);
      assert.equal(preview.fgt.recipe.rinse_water_ml, 500);
    }
    await page.screenshot({ path: `/tmp/ina-device-definition-${kind.toLowerCase()}-settings.png`, fullPage: true });

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
