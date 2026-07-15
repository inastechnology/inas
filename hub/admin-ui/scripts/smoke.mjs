import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const fieldId = "demo-strawberry-field";
const layoutUrl = `${baseUrl}/fields/${fieldId}/layout`;
const apiUrl = `${baseUrl}/local/api/fields/${fieldId}/layout`;
const deviceApiUrl = `${apiUrl}/devices`;
const plantApiUrl = `${baseUrl}/local/api/fields/${fieldId}/plantings`;

const current = await fetchJson(apiUrl);
const demoDevices = await fetchJson(deviceApiUrl);
assert.equal(demoDevices.length, 12, "demo must provide twelve bindable devices");
assert.deepEqual(
  new Set(demoDevices.map((device) => device.group_label)),
  new Set(["潅水デバイス", "環境センサー", "土壌センサー", "日射・PARセンサー", "カメラ"]),
);
assert(
  demoDevices
    .find((device) => device.id === "INADS-DEMO-WRS-001")
    ?.resources.some((resource) => resource.name === "東側点滴ライン"),
  "WRS switch resources must be available for binding",
);
const root = current.spaces.find((space) => space.id === current.root_space_id);
assert(root, "root space must exist");
await fetchJson(apiUrl, {
  method: "PUT",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    ...current,
    spaces: [{ ...root, name: "イチゴ実証圃場", north_angle_deg: 0, placements: [] }],
  }),
});

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

try {
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(layoutUrl, { waitUntil: "networkidle0" });
  await page.waitForSelector(".installation-app");
  await page.waitForSelector(".layout-canvas canvas");
  await page.type('input[aria-label="配置物を検索"]', "照明");
  assert.equal(await page.$$eval(".preset-button", (buttons) => buttons.length), 1, "palette search must narrow presets");
  assert.match(await page.$eval(".preset-button", (button) => button.textContent || ""), /植物育成ライト/);
  await page.focus('input[aria-label="配置物を検索"]');
  await page.keyboard.down("Control");
  await page.keyboard.press("A");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await page.waitForFunction(() => document.querySelectorAll(".preset-button").length > 10);
  assert.match(await page.$eval(".canvas-north-marker", (element) => element.getAttribute("aria-label") || ""), /0度/);
  await page.$eval('.north-angle-editor input[type="range"]', (input) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, "45");
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.waitForFunction(() => document.querySelector(".canvas-north-marker")?.getAttribute("aria-label")?.includes("45度"));
  await page.screenshot({ path: "/tmp/ina-layout-north-settings.png" });

  await clickPreset(page, "センサー");
  const sensorDeviceSelect = ".device-binding-section select";
  const sensorGroups = await page.$$eval(`${sensorDeviceSelect} optgroup`, (groups) => groups.map((group) => group.label));
  assert.deepEqual(
    new Set(sensorGroups),
    new Set(["環境センサー", "土壌センサー", "日射・PARセンサー", "カメラ"]),
  );
  await page.select(sensorDeviceSelect, "INADS-DEMO-ENV-001");
  await page.screenshot({ path: "/tmp/ina-layout-device-candidates.png" });

  await dragPreset(page, "ハウス");
  await page.waitForSelector(".selection-heading");
  await replaceValue(page, ".inspector-content > label input", "1号ハウス");
  await replaceValue(page, ".field-grid.four label:nth-child(3) input", "18");
  await page.click(".open-child-button");
  await page.waitForFunction(() => document.querySelectorAll(".breadcrumbs button").length === 2);

  for (let index = 0; index < 3; index += 1) {
    await clickPreset(page, "畝");
    await replaceValue(page, ".field-grid.four label:nth-child(1) input", "12");
    await replaceValue(page, ".field-grid.four label:nth-child(2) input", String(3 + index * 5));
  }
  await clickPreset(page, "潅水機");
  await replaceValue(page, ".field-grid.four label:nth-child(1) input", "4");
  await replaceValue(page, ".field-grid.four label:nth-child(2) input", "8");
  const deviceSelect = ".device-binding-section select";
  await page.select(deviceSelect, "INADS-DEMO-WTR-001");
  const firstTarget = await page.$(".target-selector label input");
  assert(firstTarget, "watering target must be selectable");
  await firstTarget.click();
  await page.screenshot({ path: "/tmp/ina-layout-device-binding.png" });

  await page.click(".save-button");
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"));
  await page.click(".breadcrumbs button:first-child");
  await page.waitForFunction(() => document.querySelectorAll(".breadcrumbs button").length === 1);

  await clickPreset(page, "鉢");
  const wateringMethodSelect = ".watering-source-section select";
  assert.equal(await page.$eval(wateringMethodSelect, (select) => select.value), "");
  assert.match(await page.$eval(`${wateringMethodSelect} option:first-child`, (option) => option.textContent || ""), /手動潅水/);
  const wateringSourceId = await page.$eval(`${wateringMethodSelect} option:nth-child(2)`, (option) => option.value);
  assert(wateringSourceId, "a placed watering device must be selectable from the medium");
  await page.select(wateringMethodSelect, wateringSourceId);
  assert.equal(await page.$eval(wateringMethodSelect, (select) => select.value), wateringSourceId);
  await page.click(".save-button");
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"));

  await page.type('.plant-registration input[placeholder="例: ブルーベリー"]', "ブルーベリー");
  await page.type('.plant-registration input[placeholder="例: オニール"]', "オニール");
  await page.select(".plant-registration select", "fruit_tree");
  await page.waitForSelector('.plant-registration input[placeholder="年"]');
  await page.type('.plant-registration input[placeholder="年"]', "3");
  await page.type('.plant-registration input[placeholder="酸性用土、培養土など"]', "ピートモス主体の酸性用土");
  await page.click(".register-button");
  await page.waitForSelector(".calendar-action");
  await page.screenshot({ path: "/tmp/ina-plant-calendar-desktop.png" });

  await page.click(".calendar-action .complete-button");
  await page.click(".calendar-action .work-rating label:nth-child(4)");
  await page.screenshot({ path: "/tmp/ina-plant-work-record-desktop.png" });
  await page.click('.calendar-action .work-record-form button[type="submit"]');
  await page.waitForSelector(".calendar-action .completed-badge");

  await page.type(".plant-question textarea", "追肥の前に何を確認すればよいですか？");
  await page.click('.plant-question button[type="submit"]');
  await page.waitForSelector(".question-answer");
  await page.click(".calendar-header .icon-button");

  await page.click('.plant-target-editor > button[type="submit"]');
  await page.waitForFunction(() => document.querySelector(".plant-target-heading")?.textContent?.includes("保存済み"));

  const desktopZoom = await page.$eval(".zoom-control span", (element) => element.textContent);
  await page.screenshot({ path: "/tmp/ina-layout-desktop.png" });
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 300));
  const mobileNorthMarker = await page.$eval(".canvas-north-marker", (element) => {
    const rect = element.getBoundingClientRect();
    return { top: rect.top, right: rect.right, bottom: rect.bottom, left: rect.left };
  });
  assert(mobileNorthMarker.top >= 0 && mobileNorthMarker.left >= 0, "north marker must remain inside the mobile viewport");
  assert(mobileNorthMarker.right <= 390 && mobileNorthMarker.bottom <= 844, "north marker must be visible on mobile");
  await page.screenshot({ path: "/tmp/ina-layout-mobile.png", fullPage: true });

  const saved = await fetchJson(apiUrl);
  const plantBundle = await fetchJson(plantApiUrl);
  const savedRoot = saved.spaces.find((space) => space.id === saved.root_space_id);
  const greenhouse = savedRoot?.placements.find((placement) => placement.preset === "greenhouse");
  const pot = savedRoot?.placements.find((placement) => placement.preset === "pot");
  const environmentSensor = savedRoot?.placements.find((placement) => placement.preset === "sensor");
  const greenhouseSpace = saved.spaces.find((space) => space.id === greenhouse?.child_space_id);
  const wateringDevice = greenhouseSpace?.placements.find((placement) => placement.preset === "watering_device");
  const blueberry = plantBundle.plantings.find((planting) => planting.placement_id === pot?.id);
  const blueberryCalendar = plantBundle.calendars[blueberry?.id];

  assert(greenhouse, "greenhouse must be created by drag and drop");
  assert.equal(savedRoot?.north_angle_deg, 45);
  assert.equal(environmentSensor?.binding?.device_id, "INADS-DEMO-ENV-001");
  assert.equal(greenhouse.name, "1号ハウス");
  assert.equal(greenhouse.width, 18);
  assert.equal(greenhouseSpace?.north_angle_deg, 45);
  assert.equal(greenhouseSpace?.placements.filter((placement) => placement.preset === "ridge").length, 3);
  assert.equal(wateringDevice?.binding?.device_id, "INADS-DEMO-WTR-001");
  assert.equal(wateringDevice?.binding?.target_placement_ids.length, 2);
  assert(wateringDevice?.binding?.target_placement_ids.includes(pot?.id), "pot must be linked from its watering method selector");
  assert(blueberry, "blueberry planting must be registered on the pot");
  assert.equal(blueberry.crop_name, "ブルーベリー");
  assert.equal(blueberry.crop_category, "fruit_tree");
  assert.equal(blueberry.tree_age_years, 3);
  assert.equal(blueberry.conditions.region, "");
  assert.equal(blueberry.growth_targets.soil_moisture_percent.max, 60);
  assert(blueberryCalendar?.actions.length > 0, "plant calendar must contain actions");
  assert(blueberryCalendar.actions.some((action) => action.status === "completed"), "work completion must be stored");
  assert(plantBundle.work_logs.some((log) => log.planting_id === blueberry.id), "work log must be stored");
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));

  process.stdout.write(
    JSON.stringify(
      {
        revision: saved.revision,
        rootPlacements: savedRoot?.placements.length,
        childSpaces: saved.spaces.length - 1,
        greenhouseRidges: greenhouseSpace?.placements.filter((placement) => placement.preset === "ridge").length,
        northAngle: savedRoot?.north_angle_deg,
        plant: blueberry.crop_name,
        calendarActions: blueberryCalendar.actions.length,
        workLogs: plantBundle.work_logs.filter((log) => log.planting_id === blueberry.id).length,
        desktopZoom,
        screenshots: ["/tmp/ina-layout-north-settings.png", "/tmp/ina-layout-device-candidates.png", "/tmp/ina-layout-device-binding.png", "/tmp/ina-layout-desktop.png", "/tmp/ina-layout-mobile.png", "/tmp/ina-plant-calendar-desktop.png", "/tmp/ina-plant-work-record-desktop.png"],
      },
      null,
      2,
    ) + "\n",
  );
} finally {
  await browser.close();
}

async function clickPreset(page, label) {
  const button = await presetButton(page, label);
  await button.click();
}

async function dragPreset(page, label) {
  const source = await presetButton(page, label);
  const target = await page.$(".layout-canvas");
  assert(source && target, "drag source and target must exist");
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  assert(sourceBox && targetBox, "drag source and target must be visible");
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(targetBox.x + targetBox.width * 0.55, targetBox.y + targetBox.height * 0.45, { steps: 12 });
  await page.mouse.up();
}

async function presetButton(page, label) {
  const buttons = await page.$$(".preset-button");
  for (const button of buttons) {
    const text = await button.evaluate((element) => element.textContent || "");
    if (text.includes(label)) return button;
  }
  throw new Error(`preset not found: ${label}`);
}

async function replaceValue(page, selector, value) {
  await page.focus(selector);
  await page.keyboard.down("Control");
  await page.keyboard.press("A");
  await page.keyboard.up("Control");
  await page.keyboard.type(value);
  await page.keyboard.press("Tab");
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request failed: ${response.status}`);
  return body;
}
