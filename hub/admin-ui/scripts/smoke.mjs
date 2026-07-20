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
assert.equal(demoDevices.length, 13, "demo must provide thirteen bindable devices including FGT");
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
  assert.equal(await page.$eval(".calendar-button", (link) => link.getAttribute("target")), "_blank", "the calendar must open without discarding layout edits");
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
  const concurrentLayout = await fetchJson(apiUrl);
  await fetchJson(apiUrl, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...concurrentLayout, name: "別画面で更新された設置ビュー" }),
  });

  await clickPreset(page, "センサー");
  const sensorDeviceSelect = ".device-binding-section .searchable-select";
  assert.equal(await page.$(`${sensorDeviceSelect} .searchable-select-search`), null, "search field must stay inside the closed dropdown");
  await page.click(`${sensorDeviceSelect} .searchable-select-control`);
  await page.type(`${sensorDeviceSelect} input[type="search"]`, "ENV-001");
  await page.waitForFunction(
    (selector) => [...document.querySelectorAll(`${selector} [data-searchable-option]`)].filter((option) => option.dataset.value).length === 1,
    {},
    sensorDeviceSelect,
  );
  assert.equal(await page.$$eval(`${sensorDeviceSelect} [data-searchable-option]`, (options) => options.filter((option) => option.dataset.value).length), 1, "device search must narrow dynamic device options");
  await replaceValue(page, `${sensorDeviceSelect} input[type="search"]`, "");
  await page.waitForFunction((selector) => document.querySelectorAll(`${selector} .searchable-select-group[aria-label]`).length >= 3, {}, sensorDeviceSelect);
  const sensorGroups = await page.$$eval(`${sensorDeviceSelect} .searchable-select-group[aria-label]`, (groups) => groups.map((group) => group.getAttribute("aria-label")));
  for (const expectedGroup of ["環境センサー", "土壌センサー", "日射・PARセンサー"]) {
    assert(sensorGroups.includes(expectedGroup), `sensor candidates must include ${expectedGroup}`);
  }
  await page.click(`${sensorDeviceSelect} [data-searchable-option][data-value="INADS-DEMO-ENV-001"]`);
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
  await chooseSearchableOption(page, ".device-binding-section .searchable-select", "INADS-DEMO-WTR-001");
  assert(await page.$('.target-selector input[aria-label*="検索"]'), "the dynamic target collection must provide search");
  await page.type('.target-selector input[aria-label*="検索"]', "一致しない培地");
  assert(await page.$(".target-selector .collection-empty"));
  await replaceValue(page, '.target-selector input[aria-label*="検索"]', "");
  const firstTarget = await page.$('.target-selector input[type="checkbox"]');
  assert(firstTarget, "watering target must be selectable");
  await firstTarget.click();
  await page.screenshot({ path: "/tmp/ina-layout-device-binding.png" });

  await page.click(".save-button");
  await page.waitForSelector(".layout-conflict-dialog");
  consumeExpectedConflict(browserErrors, "installation layout");
  assert.match(await page.$eval(".merge-success", (element) => element.textContent || ""), /自動統合/);
  await page.screenshot({ path: "/tmp/ina-layout-concurrent-merge.png" });
  await page.click(".layout-conflict-dialog footer .primary");
  await page.waitForSelector(".layout-conflict-dialog", { hidden: true });
  assert.match(await page.$eval(".save-state", (element) => element.textContent || ""), /未保存/);
  await page.click(".save-button");
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"));
  await page.click(".breadcrumbs button:first-child");
  await page.waitForFunction(() => document.querySelectorAll(".breadcrumbs button").length === 1);

  await clickPreset(page, "鉢");
  const wateringMethodSelect = ".watering-source-section .searchable-select";
  assert.match(await page.$eval(`${wateringMethodSelect} .searchable-select-control`, (button) => button.textContent || ""), /手動潅水/);
  await page.click(`${wateringMethodSelect} .searchable-select-control`);
  const wateringSourceId = await page.$eval(`${wateringMethodSelect} [data-searchable-option][data-value]:not([data-value=""])`, (option) => option.dataset.value);
  assert(wateringSourceId, "a placed watering device must be selectable from the medium");
  await page.click(`${wateringMethodSelect} [data-searchable-option][data-value="${wateringSourceId}"]`);
  assert.match(await page.$eval(`${wateringMethodSelect} .searchable-select-control`, (button) => button.textContent || ""), /潅水機/);
  await page.click(".save-button");
  await page.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"));

  await page.type('.plant-registration input[placeholder="例: ブルーベリー"]', "ブルーベリー");
  await page.type('.plant-registration input[placeholder="例: オニール"]', "オニール");
  await page.select('.plant-registration select[name="crop_category"]', "fruit_tree");
  await page.waitForSelector('.plant-registration input[placeholder="年"]');
  await page.type('.plant-registration input[placeholder="年"]', "3");
  assert.equal(await page.$eval(".register-button", (button) => button.disabled), true, "AI generation must wait for required growing conditions");
  assert.match(await page.$eval(".disabled-action-reason", (notice) => notice.textContent || ""), /用土・培地/);
  await page.select('.plant-registration select[name="soil_or_substrate"]', "acidic_blueberry_mix");
  await page.select('.plant-registration select[name="sunlight"]', "full_sun");
  assert.equal(await page.$eval(".register-button", (button) => button.disabled), false, "AI generation must enable after all required inputs are present");
  await page.click(".register-button");
  await page.waitForSelector(".calendar-kanban-card");
  await page.waitForFunction(
    () => document.querySelector("[data-calendar-edit-locked]")?.getAttribute("data-calendar-edit-locked") === "false",
    { timeout: 30_000 },
  );
  const modalRect = await page.$eval(".calendar-modal-panel", (panel) => {
    const rect = panel.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  });
  assert(modalRect.width >= 1439 && modalRect.height >= 899, "generated calendar must open as a full-screen modal");
  await page.screenshot({ path: "/tmp/ina-plant-calendar-desktop.png" });

  const completedCountBefore = Number(await page.$eval('[data-kanban-status="completed"] > header strong', (count) => count.textContent || "0"));
  const inProgressCountBefore = await page.$$("[data-kanban-status='in_progress'] .calendar-kanban-card").then((items) => items.length);
  await page.click('[data-kanban-status="planned"] .calendar-kanban-card');
  await page.waitForSelector(".calendar-action-detail-dialog .calendar-action.planned");
  await page.click(".calendar-action-detail-dialog .action-state-controls > button:first-child");
  await page.waitForSelector(".calendar-action-detail-dialog .calendar-action.in_progress");
  assert.equal(await page.$$("[data-kanban-status='in_progress'] .calendar-kanban-card").then((items) => items.length), inProgressCountBefore + 1, "started work must move to the in-progress column");
  await page.click(".calendar-action-detail-dialog .complete-button");
  await page.waitForSelector(".work-record-dialog .work-rating label:nth-child(4)");
  await page.click(".work-record-dialog .work-rating label:nth-child(4)");
  await page.screenshot({ path: "/tmp/ina-plant-work-record-desktop.png" });
  await page.click('.work-record-dialog .work-record-form button[type="submit"]');
  await page.waitForFunction((before) => Number(document.querySelector('[data-kanban-status="completed"] > header strong')?.textContent || "0") > before, {}, completedCountBefore);
  await page.waitForSelector(".calendar-action-detail-dialog .completed-badge");
  assert.equal(await page.$$("[data-kanban-status='in_progress'] .calendar-kanban-card").then((items) => items.length), inProgressCountBefore, "completed work must leave the in-progress column");
  await page.click(".calendar-action-detail-dialog > header .icon-button");

  const skippedCountBefore = Number(await page.$eval('[data-kanban-status="completed"] > header strong', (count) => count.textContent || "0"));
  await page.click('[data-kanban-status="planned"] .calendar-kanban-card');
  await page.waitForSelector(".calendar-action-detail-dialog .skip-button");
  await page.click(".calendar-action-detail-dialog .skip-button");
  await page.waitForSelector(".skip-decision-form textarea[required]");
  await page.type(".skip-decision-form textarea[required]", "葉色と新梢は良好で、現在は作業不要と確認した");
  await page.type(".skip-decision-form textarea:not([required])", "自動生成された期限切れ作業を現地確認した");
  await page.screenshot({ path: "/tmp/ina-plant-skip-decision-desktop.png" });
  await page.click('.skip-decision-form button[type="submit"]');
  await page.waitForFunction((before) => Number(document.querySelector('[data-kanban-status="completed"] > header strong')?.textContent || "0") > before, {}, skippedCountBefore);
  await page.waitForSelector(".calendar-action-detail-dialog .skipped-badge");
  assert.match(await page.$eval(".calendar-action-detail-dialog .skip-decision-record", (record) => record.textContent || ""), /現在は作業不要/);
  await page.click(".calendar-action-detail-dialog > header .icon-button");

  await page.$$eval(".calendar-workspace-tabs button", (buttons) => {
    const cropPlan = buttons.find((button) => button.textContent?.includes("作物別の栽培計画"));
    if (!(cropPlan instanceof HTMLButtonElement)) throw new Error("crop planning workspace was not found");
    cropPlan.click();
  });
  await page.type(".plant-question textarea", "追肥の前に何を確認すればよいですか？");
  await page.click('.plant-question button[type="submit"]');
  await page.waitForSelector(".plant-chat-turn");
  assert.match(await page.$eval(".plant-chat-turn", (turn) => turn.textContent || ""), /追肥の前に何を確認.*栽培アシスタント/s);
  const chatCount = await page.$$(".plant-chat-turn").then((items) => items.length);
  await page.type(".plant-chat-search input", "追肥 確認");
  await page.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 1);
  await page.click(".plant-chat-search button");
  await page.waitForFunction((expected) => document.querySelectorAll(".plant-chat-turn").length === expected, {}, chatCount);
  await page.type(".plant-question textarea", "おすすめの映画を教えて");
  await page.click('.plant-question button[type="submit"]');
  await page.waitForSelector(".plant-question .form-error");
  assert.match(await page.$eval(".plant-question .form-error", (error) => error.textContent || ""), /登録した作物と農作業の相談専用/);
  assert.equal(await page.$$(".plant-chat-turn").then((items) => items.length), chatCount, "out-of-scope questions must not be added to history");
  const expectedRejectionLog = browserErrors.findIndex((message) => message.includes("422"));
  if (expectedRejectionLog >= 0) browserErrors.splice(expectedRejectionLog, 1);
  await page.screenshot({ path: "/tmp/ina-cultivation-chat-desktop.png", fullPage: false });
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.$eval(".plant-question", (panel) => panel.scrollIntoView({ block: "start" }));
  assert((await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1, "cultivation chat must not overflow on mobile");
  await page.screenshot({ path: "/tmp/ina-cultivation-chat-mobile.png", fullPage: false });
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.click(".calendar-header .icon-button");

  if (!(await page.$('.plant-target-row.enabled input[type="range"]'))) {
    await page.click('.plant-target-row .plant-target-toggle input[type="checkbox"]');
    await page.waitForSelector('.plant-target-row.enabled input[type="range"]');
  }
  await page.$eval('.plant-target-row.enabled input[type="range"]', (input) => {
    const current = Number(input.value);
    const maximum = Number(input.max);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, String(Math.min(maximum, current + Number(input.step || 1))));
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await page.click('.plant-target-editor > button[type="submit"]');
  await page.waitForFunction(() => document.querySelector(".plant-target-heading")?.textContent?.includes("保存済み"));
  assert.equal(await page.$eval(".planting-links a:first-child", (link) => link.getAttribute("target")), "_blank");
  assert.equal(await page.$eval(".planting-links a:last-child", (link) => link.getAttribute("target")), "_blank");

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
  assert(
    [60, 65].includes(blueberry.growth_targets.soil_moisture_percent.max),
    "the saved soil-moisture target must retain either the AI suggestion or the editable beginner default",
  );
  assert(blueberryCalendar?.actions.length > 0, "plant calendar must contain actions");
  assert(blueberryCalendar.actions.some((action) => action.status === "completed"), "work completion must be stored");
  assert(blueberryCalendar.actions.some((action) => action.status === "skipped" && action.skip_decision), "skip decision must be stored");
  assert(plantBundle.work_logs.some((log) => log.planting_id === blueberry.id), "work log must be stored");

  const questionRecords = Array.from({ length: 12 }, (_, index) => {
    const sequence = 12 - index;
    return {
      id: `pagination-question-${sequence}`,
      planting_id: blueberry.id,
      question: `第${sequence}回 葉の観察では何を確認しますか？`,
      answer: `第${sequence}回の観察結果を記録し、前回との差を確認します。\n葉色と葉先の変化、水分状態を見比べます。\n新芽の伸びと病害虫の兆候も写真に残します。\n変化があれば次の作業判断へ反映します。`,
      created_at: new Date(Date.UTC(2026, 6, sequence, 1)).toISOString(),
    };
  });
  const questionRequests = [];
  const historyPage = await browser.newPage();
  historyPage.on("pageerror", (error) => browserErrors.push(error.message));
  historyPage.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });
  await historyPage.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await historyPage.setCacheEnabled(false);
  await historyPage.setRequestInterception(true);
  historyPage.on("request", async (request) => {
    try {
      const url = new URL(request.url());
      if (request.method() !== "GET" || url.pathname !== `/local/api/plantings/${blueberry.id}/questions`) {
        await request.continue();
        return;
      }
      const pageNumber = Number(url.searchParams.get("page") || "1");
      const pageSize = Number(url.searchParams.get("page_size") || "5");
      const query = (url.searchParams.get("q") || "").trim();
      questionRequests.push({ page: pageNumber, pageSize, query });
      const terms = query.toLocaleLowerCase("ja").split(/\s+/).filter(Boolean);
      const matching = questionRecords.filter((record) => {
        const searchable = `${record.question} ${record.answer}`.toLocaleLowerCase("ja");
        return terms.every((term) => searchable.includes(term));
      });
      const start = (pageNumber - 1) * pageSize;
      const items = matching.slice(start, start + pageSize);
      const pageCount = Math.max(1, Math.ceil(matching.length / pageSize));
      await request.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items,
          total: matching.length,
          page: pageNumber,
          page_size: pageSize,
          page_count: pageCount,
          has_previous: pageNumber > 1,
          has_next: pageNumber < pageCount,
        }),
      });
    } catch (error) {
      browserErrors.push(String(error));
      await request.abort("failed");
    }
  });
  await historyPage.goto(`${baseUrl}/fields/${fieldId}/calendar?planting=${blueberry.id}`, { waitUntil: "networkidle0" });
  await historyPage.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 5);
  assert.deepEqual(questionRequests[0], { page: 1, pageSize: 5, query: "" }, "chat history must initially request only the latest five records");
  await historyPage.$eval(".plant-chat-history", (history) => history.scrollTo({ top: 0, behavior: "instant" }));
  await historyPage.waitForFunction(() => (document.querySelector(".plant-chat-history")?.scrollTop ?? 100) <= 32);
  await historyPage.$eval(".plant-chat-history", (history) => history.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: -120 })));
  await historyPage.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 10 && document.querySelector(".plant-chat-history")?.getAttribute("data-question-page") === "2");
  assert((await historyPage.$eval(".plant-chat-history", (history) => history.scrollTop)) > 0, "loading older chat records must preserve the visible scroll position");
  await historyPage.$eval(".plant-chat-history", (history) => history.scrollTo({ top: 0, behavior: "instant" }));
  await historyPage.waitForFunction(() => (document.querySelector(".plant-chat-history")?.scrollTop ?? 100) <= 32);
  await historyPage.$eval(".plant-chat-history", (history) => history.dispatchEvent(new WheelEvent("wheel", { bubbles: true, deltaY: -120 })));
  await historyPage.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 12 && document.querySelector(".plant-chat-history")?.getAttribute("data-question-page") === "3");
  assert.deepEqual(questionRequests.slice(0, 3).map(({ page, pageSize }) => ({ page, pageSize })), [{ page: 1, pageSize: 5 }, { page: 2, pageSize: 5 }, { page: 3, pageSize: 5 }]);
  await replaceValue(historyPage, ".plant-chat-search input", "第1回 葉");
  await historyPage.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 1);
  assert.deepEqual(questionRequests.at(-1), { page: 1, pageSize: 5, query: "第1回 葉" }, "chat search must stay server-side and use the same five-record page size");
  await historyPage.screenshot({ path: "/tmp/ina-cultivation-chat-pagination.png", fullPage: false });
  await historyPage.click(".plant-chat-search button");
  await historyPage.waitForFunction(() => document.querySelectorAll(".plant-chat-turn").length === 5);
  await historyPage.close();

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
        screenshots: ["/tmp/ina-layout-north-settings.png", "/tmp/ina-layout-device-candidates.png", "/tmp/ina-layout-device-binding.png", "/tmp/ina-layout-concurrent-merge.png", "/tmp/ina-layout-desktop.png", "/tmp/ina-layout-mobile.png", "/tmp/ina-plant-calendar-desktop.png", "/tmp/ina-plant-work-record-desktop.png", "/tmp/ina-plant-skip-decision-desktop.png", "/tmp/ina-cultivation-chat-pagination.png"],
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

function consumeExpectedConflict(errors, label) {
  const index = errors.findIndex((message) => message.includes("409 (CONFLICT)"));
  assert.notEqual(index, -1, `${label} must produce an HTTP 409 before merge`);
  errors.splice(index, 1);
}

async function dragPreset(page, label) {
  const source = await presetButton(page, label);
  const target = await page.$(".layout-canvas");
  assert(source && target, "drag source and target must exist");
  await page.evaluate((sourceElement, targetElement) => {
    const transfer = new DataTransfer();
    const sourceBox = sourceElement.getBoundingClientRect();
    const targetBox = targetElement.getBoundingClientRect();
    sourceElement.dispatchEvent(new DragEvent("dragstart", {
      bubbles: true,
      cancelable: true,
      dataTransfer: transfer,
      clientX: sourceBox.left + sourceBox.width / 2,
      clientY: sourceBox.top + sourceBox.height / 2,
    }));
    targetElement.dispatchEvent(new DragEvent("dragover", {
      bubbles: true,
      cancelable: true,
      dataTransfer: transfer,
      clientX: targetBox.left + targetBox.width * 0.55,
      clientY: targetBox.top + targetBox.height * 0.45,
    }));
    targetElement.dispatchEvent(new DragEvent("drop", {
      bubbles: true,
      cancelable: true,
      dataTransfer: transfer,
      clientX: targetBox.left + targetBox.width * 0.55,
      clientY: targetBox.top + targetBox.height * 0.45,
    }));
    sourceElement.dispatchEvent(new DragEvent("dragend", { bubbles: true, dataTransfer: transfer }));
  }, source, target);
  await page.waitForSelector(".open-child-button");
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
  await page.$eval(selector, (control, nextValue) => {
    const prototype = control instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    setter?.call(control, nextValue);
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
    control.blur();
  }, value);
}

async function chooseSearchableOption(page, rootSelector, value) {
  if (!(await page.$(`${rootSelector}.open`))) await page.click(`${rootSelector} .searchable-select-control`);
  await page.waitForSelector(`${rootSelector} [data-searchable-option][data-value="${value}"]`);
  await page.click(`${rootSelector} [data-searchable-option][data-value="${value}"]`);
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request failed: ${response.status}`);
  return body;
}
