import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const fieldId = "demo-strawberry-field";
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });

async function dragCardToColumn(targetPage, actionId, column) {
  await targetPage.evaluate((id) => {
    const source = document.querySelector(`.calendar-kanban-card[data-action-id="${CSS.escape(id)}"]`);
    if (!(source instanceof HTMLButtonElement)) throw new Error("drag source was not found");
    const transfer = new DataTransfer();
    source.dispatchEvent(new DragEvent("dragstart", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, actionId);
  await new Promise((resolve) => setTimeout(resolve, 80));
  await targetPage.evaluate((destination) => {
    const target = document.querySelector(`[data-kanban-status="${destination}"]`);
    if (!(target instanceof HTMLElement)) throw new Error("drag target was not found");
    const transfer = new DataTransfer();
    target.dispatchEvent(new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: transfer }));
    target.dispatchEvent(new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, column);
  await new Promise((resolve) => setTimeout(resolve, 80));
  await targetPage.evaluate((id) => {
    const source = document.querySelector(`.calendar-kanban-card[data-action-id="${CSS.escape(id)}"]`);
    if (!(source instanceof HTMLButtonElement)) return;
    const transfer = new DataTransfer();
    source.dispatchEvent(new DragEvent("dragend", { bubbles: true, cancelable: true, dataTransfer: transfer }));
  }, actionId);
}

async function selectCalendarWorkspace(targetPage, label) {
  await targetPage.$$eval(".calendar-workspace-tabs button", (buttons, text) => {
    const button = buttons.find((item) => item.textContent?.includes(text));
    if (!(button instanceof HTMLButtonElement)) throw new Error(`calendar workspace was not found: ${text}`);
    button.click();
  }, label);
}

try {
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields/${fieldId}`, { waitUntil: "networkidle0" });
  assert.equal(await page.$$eval("[data-field-tab]", (tabs) => tabs.length), 5);
  assert.equal(await page.$eval("#field-installation-tree", (details) => details.hasAttribute("open")), false);
  const targetSettingsHref = await page.$eval("#field-status-dashboard .range-card", (link) => link.href);
  assert.equal(await page.$eval("#field-status-dashboard .range-card", (link) => link.getAttribute("target")), "_blank");
  const targetSettingsUrl = new URL(targetSettingsHref);
  const targetMetric = targetSettingsUrl.searchParams.get("target_metric");
  assert(targetMetric, "an environment metric must carry its target metric to the editor");
  const targetPage = await browser.newPage();
  await targetPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await targetPage.goto(targetSettingsHref, { waitUntil: "networkidle0" });
  await targetPage.waitForSelector(`.plant-target-row.focused[data-target-metric="${targetMetric}"]`);
  assert(await targetPage.$(".inspector-panel .active-planting"), "the metric link must select the target planting");
  await targetPage.screenshot({ path: "/tmp/ina-environment-target-direct.png", fullPage: true });
  await targetPage.close();
  const placementDetailHref = await page.$eval("#field-installation-tree .tree-row.kind-cultivation", (link) => link.href);
  const placementDetailUrl = new URL(placementDetailHref);
  assert.match(placementDetailUrl.pathname, /\/layout$/);
  assert(placementDetailUrl.searchParams.get("space"));
  assert(placementDetailUrl.searchParams.get("placement"));
  assert.match(await page.$eval("#field-installation-tree .tree-row.kind-device", (link) => link.getAttribute("href") || ""), /^\/mqtt-devices\//);
  const placementPage = await browser.newPage();
  await placementPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await placementPage.goto(placementDetailHref, { waitUntil: "networkidle0" });
  await placementPage.waitForSelector(".inspector-panel .inspector-content");
  const selectedPlacementName = await placementPage.$eval(".inspector-panel input", (input) => input.value);
  assert(selectedPlacementName, "the linked placement must be selected in the installation editor");
  await placementPage.close();
  assert.match(await page.$eval("#field-action-candidates", (panel) => panel.textContent || ""), /作業TODO/);
  assert.match(await page.$eval("#field-action-candidates", (panel) => panel.textContent || ""), /(そろそろ|今やる|期限超過)/);
  await page.screenshot({ path: "/tmp/ina-field-todo-desktop.png", fullPage: true });
  const calendarHref = await page.$eval(".calendar-task", (link) => link.href);
  assert.equal(await page.$eval(".calendar-task", (link) => link.getAttribute("target")), "_blank");
  const todoActionId = new URL(calendarHref).searchParams.get("action");
  assert(todoActionId, "a TODO link must identify the selected action");
  const calendarPage = await browser.newPage();
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await calendarPage.goto(calendarHref, { waitUntil: "networkidle0" });
  await calendarPage.waitForSelector(`.calendar-action-detail-dialog .calendar-action[data-action-id="${todoActionId}"]`);
  await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  assert.match(new URL(calendarPage.url()).pathname, /\/calendar$/);
  const agenticExamples = await calendarPage.evaluate(async (activeFieldId) => {
    const response = await fetch(`/local/api/fields/${encodeURIComponent(activeFieldId)}/plantings`);
    const bundle = await response.json();
    const result = {};
    const activePlantingIds = new Set((bundle.plantings || []).filter((planting) => planting.status === "active").map((planting) => planting.id));
    for (const [plantingId, calendar] of Object.entries(bundle.calendars || {})) {
      if (!activePlantingIds.has(plantingId)) continue;
      for (const action of calendar.actions || []) {
        const readiness = bundle.operation_readiness?.[action.id];
        if (action.action_type === "watering" && readiness?.executor_candidates?.length && !result.watering) result.watering = { plantingId, actionId: action.id };
        if (["pruning", "harvest", "repotting"].includes(action.action_type) && readiness?.executor_mode === "human" && !result.human) result.human = { plantingId, actionId: action.id };
      }
    }
    return result;
  }, fieldId);
  assert(agenticExamples.watering, "the demo must include a watering action with a physically linked device");
  await calendarPage.goto(`${baseUrl}/fields/${fieldId}/calendar?planting=${agenticExamples.watering.plantingId}&action=${agenticExamples.watering.actionId}`, { waitUntil: "networkidle0" });
  await calendarPage.waitForSelector(".calendar-action-detail-dialog .agentic-operation-readiness.device_assisted");
  assert.match(await calendarPage.$eval(".agentic-operation-readiness", (panel) => panel.textContent || ""), /接続済みの機器を利用できます.*デモ潅水機1.*始める前.*この場合は止める.*終わったら.*自動実行はまだ行いません/s);
  assert.equal(await calendarPage.$eval(".agentic-executor-list a", (link) => link.getAttribute("target")), "_blank", "device settings must preserve the open calendar work");
  await calendarPage.$eval(".agentic-operation-readiness", (panel) => panel.scrollIntoView({ block: "center" }));
  await calendarPage.screenshot({ path: "/tmp/ina-agentic-watering-readiness.png", fullPage: false });
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  await calendarPage.$eval(".agentic-operation-readiness", (panel) => panel.scrollIntoView({ block: "start" }));
  assert((await calendarPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1, "watering readiness must not overflow on mobile");
  await calendarPage.screenshot({ path: "/tmp/ina-agentic-watering-readiness-mobile.png", fullPage: false });
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  assert(agenticExamples.human, "the demo must include a human-guided pruning, harvest, or repotting action");
  await calendarPage.goto(`${baseUrl}/fields/${fieldId}/calendar?planting=${agenticExamples.human.plantingId}&action=${agenticExamples.human.actionId}`, { waitUntil: "networkidle0" });
  await calendarPage.waitForSelector(".calendar-action-detail-dialog .agentic-operation-readiness.human");
  assert.match(await calendarPage.$eval(".agentic-operation-readiness", (panel) => panel.textContent || ""), /人が確認して実施します.*自動実行はまだ行いません/s);
  await calendarPage.$eval(".agentic-operation-readiness", (panel) => panel.scrollIntoView({ block: "center" }));
  await calendarPage.screenshot({ path: "/tmp/ina-agentic-human-readiness.png", fullPage: false });
  await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  assert.equal(await calendarPage.$$(".installation-app").then((items) => items.length), 0, "calendar page must not mount the installation editor");
  assert.match(await calendarPage.$eval(".calendar-workspace-tabs button.active", (button) => button.textContent || ""), /圃場の作業/);
  assert.match(await calendarPage.$eval(".calendar-work-scope", (scope) => scope.textContent || ""), /圃場のすべての作物/, "the work board must offer all crops in the field");
  assert.equal(await calendarPage.$$(".calendar-section-heading small").then((items) => items.filter((item) => /^r\d+/.test(item.textContent || "")).length), 0, "internal calendar revisions must stay hidden");
  await selectCalendarWorkspace(calendarPage, "作物別の栽培計画");
  await calendarPage.evaluate(() => { const shell = document.querySelector('.calendar-page-shell'); if (shell instanceof HTMLElement) shell.scrollTop = 0; });
  await calendarPage.click(".care-profile-summary > summary");
  await calendarPage.waitForSelector(".care-evidence a");
  assert.equal(await calendarPage.$$(".care-evidence a").then((items) => items.length), 2, "the demo plan must show its public evidence sources");
  assert.equal(await calendarPage.$eval(".care-evidence a", (link) => link.getAttribute("target")), "_blank", "evidence must open without losing the calendar");
  assert.match(await calendarPage.$eval(".care-evidence", (panel) => panel.textContent || ""), /農林水産省.*農研機構/s);
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-crop-plan-desktop.png", fullPage: true });
  await calendarPage.click(".calendar-generation .calendar-section-heading button");
  await calendarPage.waitForSelector('.calendar-generation-dialog .generation-mode-options input[value="review"]:checked');
  await new Promise((resolve) => setTimeout(resolve, 250));
  assert.equal(await calendarPage.$eval(".calendar-generation-dialog", (dialog) => dialog.getAttribute("aria-modal")), "true", "AI regeneration must open as a modal");
  assert.equal(await calendarPage.$$(".generation-mode-options label").then((items) => items.length), 2, "regeneration must offer review and automatic modes");
  assert.match(await calendarPage.$eval(".calendar-generation-dialog form", (form) => form.textContent || ""), /現在の.*件の作業.*重複させません/s);
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-regeneration-modes.png", fullPage: false });
  await calendarPage.click('.calendar-generation-dialog .form-actions button[type="button"]');
  await calendarPage.waitForFunction(() => !document.querySelector(".calendar-generation-dialog"));
  assert.equal(await calendarPage.$$(".gantt-period-controls").then((items) => items.length), 1);
  assert.match(await calendarPage.$eval(".fertilizer-effect-panel", (panel) => panel.textContent || ""), /培地の施肥と残存肥効/);
  const fertilizerCount = await calendarPage.$$(".fertilizer-history-list article").then((items) => items.length);
  await calendarPage.$$eval(".fertilizer-effect-panel .calendar-section-heading button", (buttons) => buttons.find((button) => button.textContent?.includes("肥料カタログ"))?.click());
  await calendarPage.waitForSelector(".fertilizer-catalog-dialog");
  await new Promise((resolve) => setTimeout(resolve, 250));
  assert.equal(await calendarPage.$$(".fertilizer-catalog-sections section:first-child .fertilizer-material-card").then((items) => items.length), 7, "the built-in catalog must come from the Hub");
  assert.match(await calendarPage.$eval(".fertilizer-catalog-sections", (panel) => panel.textContent || ""), /瀬戸内いちご有機配合/);
  assert.match(await calendarPage.$eval(".fertilizer-catalog-intro", (panel) => panel.textContent || ""), /製品ラベルや分析結果を優先/);
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-catalog-desktop.png", fullPage: false });
  await calendarPage.click(".fertilizer-catalog-intro button");
  await calendarPage.waitForSelector(".fertilizer-catalog-form");
  assert.equal(await calendarPage.$eval(".fertilizer-advanced-fields", (details) => details.hasAttribute("open")), false, "advanced fertilizer estimates must be collapsed initially");
  assert.match(await calendarPage.$eval(".fertilizer-catalog-form", (form) => form.textContent || ""), /袋の「保証成分量」.*上級者向け/s);
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-catalog-add.png", fullPage: false });
  await calendarPage.click('.fertilizer-catalog-form .form-actions button[type="button"]');
  await calendarPage.waitForSelector(".fertilizer-catalog-sections");
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-catalog-mobile.png", fullPage: false });
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await calendarPage.click(".fertilizer-catalog-dialog > header .icon-button");
  await calendarPage.waitForFunction(() => !document.querySelector(".fertilizer-catalog-dialog"));
  await calendarPage.$$eval(".fertilizer-effect-panel .calendar-section-heading button", (buttons) => buttons.find((button) => button.textContent?.includes("施肥履歴を追加"))?.click());
  await calendarPage.waitForSelector("[data-fertilizer-form]");
  await new Promise((resolve) => setTimeout(resolve, 250));
  assert.equal(await calendarPage.$eval(".fertilizer-entry-dialog", (dialog) => dialog.getAttribute("aria-modal")), "true", "fertilizer entry must open as a modal");
  assert.equal(await calendarPage.$eval(".fertilizer-entry-dialog", (dialog) => dialog.parentElement?.parentElement === document.body), true, "fertilizer modal must be portaled above the calendar page");
  assert.equal(await calendarPage.$eval(".fertilizer-entry-dialog", (dialog) => getComputedStyle(dialog.parentElement).position), "fixed", "fertilizer modal backdrop must cover the viewport");
  assert.match(await calendarPage.$eval("[data-fertilizer-form]", (form) => form.textContent || ""), /製品kgと養分kgを分けて計算/);
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-entry-modal.png", fullPage: false });
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] select[name="fertilizer_material"]', (select) => select.options.length), 8, "Hub fertilizer materials must be available");
  await calendarPage.select('[data-fertilizer-form] select[name="material_kind"]', "poultry_manure");
  await calendarPage.waitForFunction(() => document.querySelector('[data-fertilizer-form] select[name="fertilizer_material"]')?.value === "builtin:poultry-manure-reference");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="n_percent"]', (input) => input.value), "2.5");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="p2o5_percent"]', (input) => input.value), "6.6");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="k2o_percent"]', (input) => input.value), "3.6");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="mgo_percent"]', (input) => input.value), "1.4");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="annual_available_percent"]', (input) => input.value), "50");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="effect_years"]', (input) => input.value), "1");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] input[name="start_delay_days"]', (input) => input.value), "7");
  assert.doesNotMatch(await calendarPage.$eval("[data-fertilizer-form]", (form) => form.textContent || ""), /牛ふんの10%/);
  assert.match(await calendarPage.$eval("[data-fertilizer-form]", (form) => form.textContent || ""), /鶏ふん堆肥（公的資料の平均例）の50%は編集可能な開始値/);
  await calendarPage.$eval("[data-fertilizer-form]", (form) => form.scrollIntoView({ block: "start" }));
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-preset-poultry.png", fullPage: false });
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await calendarPage.$eval("[data-fertilizer-form]", (form) => form.scrollIntoView({ block: "start" }));
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-preset-poultry-mobile.png", fullPage: false });
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  const presetExpectations = [
    ["builtin:cattle-manure-reference", "1.2", "1.3", "1.6", "10", "3", "14"],
    ["builtin:poultry-manure-reference", "2.5", "6.6", "3.6", "50", "1", "7"],
    ["builtin:dried-poultry-manure", "3.6", "4", "2.2", "60", "1", "3"],
    ["builtin:rice-straw-compost", "0.5", "0", "0", "1", "3", "21"],
    ["builtin:rapeseed-oil-cake", "5.2", "2", "1", "50", "1", "7"],
    ["builtin:fish-meal", "11", "7", "1.7", "50", "1", "7"],
    ["builtin:compound-8-8-8", "8", "8", "8", "100", "1", "0"],
  ];
  for (const [presetId, n, p2o5, k2o, available, years, delay] of presetExpectations) {
    await calendarPage.select('[data-fertilizer-form] select[name="fertilizer_material"]', presetId);
    const actual = await calendarPage.$eval("[data-fertilizer-form]", (form) => [
      form.querySelector('input[name="n_percent"]')?.value,
      form.querySelector('input[name="p2o5_percent"]')?.value,
      form.querySelector('input[name="k2o_percent"]')?.value,
      form.querySelector('input[name="annual_available_percent"]')?.value,
      form.querySelector('input[name="effect_years"]')?.value,
      form.querySelector('input[name="start_delay_days"]')?.value,
    ]);
    assert.deepEqual(actual, [n, p2o5, k2o, available, years, delay], `${presetId} must apply all reference values`);
  }
  await calendarPage.select('[data-fertilizer-form] select[name="fertilizer_material"]', "builtin:poultry-manure-reference");
  await calendarPage.waitForFunction(() => document.querySelector('[data-fertilizer-form] input[name="mgo_percent"]')?.value === "1.4");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="amount_kg"]', "20");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="n_percent"]', "2");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="p2o5_percent"]', "1");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="k2o_percent"]', "1.5");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="mgo_percent"]', "0.5");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="material_name"]', `鶏ふん堆肥 UI試験 ${Date.now()}`);
  assert.equal(await calendarPage.$eval("[data-fertilizer-form]", (form) => form.checkValidity()), true, "the fertilizer preset must leave a submittable form");
  assert.equal(await calendarPage.$eval('[data-fertilizer-form] button[type="submit"]', (button) => button.disabled), false, "the fertilizer save action must be available");
  await calendarPage.click('[data-fertilizer-form] button[type="submit"]');
  await calendarPage.waitForFunction((before) => document.querySelectorAll(".fertilizer-history-list article").length > before, {}, fertilizerCount);
  assert.match(await calendarPage.$eval(".fertilizer-balance", (panel) => panel.textContent || ""), /N.*P₂O₅.*K₂O/);
  assert.match(await calendarPage.$eval(".fertilizer-balance", (panel) => panel.textContent || ""), /MgO/);
  assert.match(await calendarPage.$eval(".fertilizer-history-list", (panel) => panel.textContent || ""), /N 2%.*MgO（苦土） 0.5%/s);
  assert.match(await calendarPage.$eval(".fertilizer-caution", (panel) => panel.textContent || ""), /土壌分析.*EC.*収穫品質/);
  await calendarPage.$eval(".fertilizer-effect-panel", (section) => section.scrollIntoView({ block: "start" }));
  await calendarPage.screenshot({ path: "/tmp/ina-fertilizer-effect-desktop.png", fullPage: false });
  await selectCalendarWorkspace(calendarPage, "圃場の作業");
  await calendarPage.waitForSelector(".calendar-kanban-card");
  await calendarPage.evaluate(() => { const shell = document.querySelector('.calendar-page-shell'); if (shell instanceof HTMLElement) shell.scrollTop = 0; });
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-workboard-desktop.png", fullPage: true });
  assert(await calendarPage.$eval(".calendar-kanban-toolbar > :first-child", (element) => element.classList.contains("calendar-action-date")), "the work date filter must be the leftmost control");
  assert.equal(await calendarPage.$$(".calendar-kanban-column").then((items) => items.length), 3, "the work board must always show three states");
  assert.match(await calendarPage.$eval('[data-kanban-status="planned"] > header', (header) => header.textContent || ""), /未完了.*人時/);
  assert.match(await calendarPage.$eval('[data-kanban-status="in_progress"] > header', (header) => header.textContent || ""), /作業中.*人時/);
  assert.match(await calendarPage.$eval('[data-kanban-status="completed"] > header', (header) => header.textContent || ""), /完了.*人時/);
  assert.equal(await calendarPage.$$(".calendar-action").then((items) => items.length), 0, "full work details must stay closed until a summary card is selected");
  const cardCountBeforeFilter = await calendarPage.$$(".calendar-kanban-card").then((items) => items.length);
  assert(cardCountBeforeFilter > 1, "the demo calendar must contain multiple searchable tasks");
  await calendarPage.type('.calendar-kanban-toolbar input[type="search"]', "一致しない作業名");
  await calendarPage.waitForFunction(() => document.querySelectorAll(".calendar-kanban-card").length === 0);
  assert.match(await calendarPage.$eval(".calendar-kanban-toolbar output", (output) => output.textContent || ""), /^0 \/ /);
  await replaceValue(calendarPage, '.calendar-kanban-toolbar input[type="search"]', "");
  await calendarPage.waitForFunction((expected) => document.querySelectorAll(".calendar-kanban-card").length === expected, {}, cardCountBeforeFilter);
  const filterDate = await calendarPage.$eval('.calendar-kanban-card time', (time) => time.getAttribute("datetime"));
  await replaceValue(calendarPage, '.calendar-action-date input[type="date"]', filterDate);
  assert(await calendarPage.$$(".calendar-kanban-card").then((items) => items.length) > 0, "the date filter must retain work whose period includes the selected day");
  await calendarPage.click('.calendar-action-date button');

  await calendarPage.click('.calendar-action-list .calendar-section-heading button');
  await calendarPage.waitForSelector('.calendar-action-create-dialog .new-action-form');
  assert.match(await calendarPage.$eval('.calendar-action-create-dialog', (dialog) => dialog.textContent || ""), /対象の作物.*今日やること.*写真つき作業メモ/s);
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-add-action-modal.png", fullPage: true });
  await calendarPage.click('.calendar-action-create-dialog > header .icon-button');

  const draggableActionId = await calendarPage.$eval('[data-kanban-status="planned"] .calendar-kanban-card', (card) => card.getAttribute("data-action-id"));
  assert(draggableActionId, "a planned task must be available for drag and drop");
  await dragCardToColumn(calendarPage, draggableActionId, "in_progress");
  await calendarPage.waitForSelector(`[data-kanban-status="in_progress"] .calendar-kanban-card[data-action-id="${draggableActionId}"]`);
  await dragCardToColumn(calendarPage, draggableActionId, "planned");
  await calendarPage.waitForSelector(`[data-kanban-status="planned"] .calendar-kanban-card[data-action-id="${draggableActionId}"]`);
  assert.equal(
    await calendarPage.$$(".calendar-kanban-card .kanban-card-workload").then((items) => items.length),
    await calendarPage.$$(".calendar-kanban-card").then((items) => items.length),
    "every summary card must show people and estimated time",
  );
  const urgencyOrder = await calendarPage.$$eval('[data-kanban-status="planned"] .calendar-kanban-card', (cards) => cards.map((card) => {
    const badge = card.querySelector(".timing-badge");
    if (badge?.classList.contains("overdue")) return 0;
    if (badge?.classList.contains("due")) return 1;
    if (badge?.classList.contains("upcoming")) return 2;
    return 3;
  }));
  assert.deepEqual(urgencyOrder, [...urgencyOrder].sort((left, right) => left - right), "incomplete work must be sorted by urgency");
  await selectCalendarWorkspace(calendarPage, "作物別の栽培計画");
  const completedGanttBar = await calendarPage.$(".gantt-bar.completed");
  if (completedGanttBar) {
    await completedGanttBar.click();
    await calendarPage.waitForSelector(".calendar-action-detail-dialog .calendar-action.completed");
    assert(await calendarPage.$(".calendar-action-detail-dialog .completed-badge"), "a completed gantt item must open its detail");
    await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  }
  await selectCalendarWorkspace(calendarPage, "圃場の作業");
  await calendarPage.click(".calendar-kanban-card");
  await calendarPage.waitForSelector(".calendar-action-detail-dialog .work-guidance");
  assert.equal(await calendarPage.$$(".calendar-action-detail-dialog .action-flow-step").then((items) => items.length), 3, "action detail must show the three-step decision flow");
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .action-decision-flow", (panel) => panel.textContent || ""), /この作業を考えたきっかけ.*やるか、今日は見送るか.*今日やること/s);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .action-flow-step.task", (panel) => panel.textContent || ""), /いちばん大切なところ.*今日やること/s);
  if (await calendarPage.$(".calendar-action-detail-dialog .calendar-action.planned")) {
    assert.equal(await calendarPage.$(".calendar-action-detail-dialog .complete-button"), null, "planned work must not offer completion recording");
    assert(await calendarPage.$(".calendar-action-detail-dialog .start-button"), "planned work must offer a start action");
    await calendarPage.click(".calendar-action-detail-dialog .action-edit-button");
    await calendarPage.waitForSelector(".action-edit-dialog .rich-action-content");
    await new Promise((resolve) => setTimeout(resolve, 250));
    assert.match(await calendarPage.$eval(".action-edit-dialog > header", (header) => header.textContent || ""), /実績入力とは別に編集/);
    assert(await calendarPage.$('.action-edit-dialog .rich-action-editor[contenteditable="true"]'), "detailed notes must use a visual rich text editor");
    assert.equal(await calendarPage.$(".action-edit-dialog .rich-action-content textarea"), null, "users must not edit raw HTML tags");
    assert.equal(await calendarPage.$$(".action-edit-dialog .rich-action-toolbar button").then((items) => items.length), 8, "the visual editor must expose its formatting tools");
    await calendarPage.$eval(".action-edit-dialog .rich-action-editor", (editor) => {
      editor.innerHTML = "<p>写真を残して変化を比べる</p>";
      editor.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText" }));
      const text = editor.querySelector("p")?.firstChild;
      if (!text) throw new Error("rich editor test text was not created");
      const range = document.createRange();
      range.setStart(text, 0);
      range.setEnd(text, 5);
      const selection = window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    });
    await calendarPage.click(".action-edit-dialog .rich-action-toolbar .marker-tool");
    assert(await calendarPage.$(".action-edit-dialog .rich-action-editor mark"), "marker tool must visibly format selected text");
    const richImageInput = await calendarPage.$('.action-edit-dialog .rich-action-image-input input[type="file"]');
    assert(richImageInput, "rich editor must provide an image picker");
    await richImageInput.uploadFile("../src/ina_device_hub/static/plant-actions/pest-control.webp");
    await calendarPage.waitForSelector(".action-edit-dialog .rich-action-editor .pending-editor-image");
    assert.equal((await calendarPage.$eval(".action-edit-dialog .rich-action-editor", (editor) => editor.textContent || "")).includes("{{image:"), false, "image markers must be presented visually instead of as HTML text");
    await calendarPage.evaluate(() => window.getSelection()?.removeAllRanges());
    await calendarPage.screenshot({ path: "/tmp/ina-calendar-edit-action-modal.png", fullPage: true });
    await calendarPage.click(".action-edit-dialog > header .icon-button");
    const deleteConfirmation = new Promise((resolve) => calendarPage.once("dialog", async (dialog) => { assert.match(dialog.message(), /元に戻せません/); await dialog.dismiss(); resolve(); }));
    await calendarPage.click(".calendar-action-detail-dialog .action-icon-button.danger");
    await deleteConfirmation;
    await calendarPage.screenshot({ path: "/tmp/ina-calendar-planned-action.png", fullPage: true });
  }
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .action-flow-step.decision", (panel) => panel.textContent || ""), /やる目安/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /見る場所/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /ここまでできたら完了/);
  assert.doesNotMatch(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /開始条件/, "decision conditions must not be repeated in the lower guide");
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-method-detail[open]", (panel) => panel.textContent || ""), /手順/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-method-detail[open]", (panel) => panel.textContent || ""), /頻度/);
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 150));
  assert((await calendarPage.$eval(".calendar-action-detail-dialog", (dialog) => dialog.scrollWidth - dialog.clientWidth)) <= 1, "mobile action detail must not overflow horizontally");
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-action-journal-mobile.png", fullPage: true });
  await calendarPage.$eval(".calendar-action-detail-dialog .action-flow-step.task", (step) => step.scrollIntoView({ block: "center" }));
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-action-journal-mobile-task.png", fullPage: true });
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  await selectCalendarWorkspace(calendarPage, "作物別の栽培計画");
  await calendarPage.$eval('.gantt-period-controls input[type="month"]', (input) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, "2025-07");
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await calendarPage.select(".gantt-period-controls select", "24");
  assert.match(await calendarPage.$eval(".gantt-period-controls output", (output) => output.textContent || ""), /2025年7月.*2027年6月/);
  assert.equal(await calendarPage.$$(".gantt-today").then((items) => items.length), 1, "gantt must mark today inside the selected period");
  await calendarPage.click(".care-profile-summary > summary");
  assert.match(await calendarPage.$eval(".care-profile-summary", (panel) => panel.textContent || ""), /EC/);
  assert.match(await calendarPage.$eval(".care-profile-summary", (panel) => panel.textContent || ""), /実施日起点/);
  await calendarPage.screenshot({ path: "/tmp/ina-care-profile-desktop.png", fullPage: true });
  await selectCalendarWorkspace(calendarPage, "圃場の作業");
  const openedWorkRecord = await calendarPage.evaluate(() => {
    const cards = [...document.querySelectorAll(".calendar-kanban-card")];
    const card = cards.find((item) => item.textContent?.includes("追肥") && item.getAttribute("data-action-status") !== "completed")
      || cards.find((item) => ["planned", "in_progress"].includes(item.getAttribute("data-action-status") || ""));
    if (!(card instanceof HTMLButtonElement)) return false;
    card.click();
    return true;
  });
  if (openedWorkRecord) {
    if (await calendarPage.$(".calendar-action-detail-dialog .calendar-action.planned")) {
      await calendarPage.click(".calendar-action-detail-dialog .start-button");
      await calendarPage.waitForSelector(".calendar-action-detail-dialog .calendar-action.in_progress");
    }
    await calendarPage.waitForSelector(".calendar-action-detail-dialog .complete-button");
    await calendarPage.click(".calendar-action-detail-dialog .complete-button");
    await calendarPage.waitForSelector(".work-record-dialog .work-detail-fields");
    await new Promise((resolve) => setTimeout(resolve, 250));
    assert.equal(await calendarPage.$eval(".work-record-dialog", (dialog) => dialog.getAttribute("aria-modal")), "true", "work records must open as a modal");
    const workMethodSelect = ".work-record-dialog .work-detail-fields .searchable-select";
    assert.equal(await calendarPage.$(`${workMethodSelect} input[type="search"]`), null, "work method search must be inside the closed dropdown");
    await calendarPage.click(`${workMethodSelect} .searchable-select-control`);
    await calendarPage.waitForSelector(`${workMethodSelect} input[type="search"]`);
    await calendarPage.type(`${workMethodSelect} input[type="search"]`, "一致しない方法");
    assert(await calendarPage.$(`${workMethodSelect} [data-searchable-option][data-value="custom"]`), "custom method must remain available while filtering");
    await calendarPage.click(`${workMethodSelect} [data-searchable-option][data-value="custom"]`);
    await calendarPage.select('.work-record-dialog .work-detail-fields select', "material_application");
    assert.match(await calendarPage.$eval(".work-record-dialog .work-detail-fields", (fields) => fields.textContent || ""), /実施内容/);
    assert.match(await calendarPage.$eval(".work-record-dialog .work-detail-fields", (fields) => fields.textContent || ""), /使用した資材・製品/);
    assert.match(await calendarPage.$eval(".work-record-dialog .work-detail-fields", (fields) => fields.textContent || ""), /実際の使用量・希釈・処理時間/);
    assert.match(await calendarPage.$eval(".work-record-dialog .work-detail-fields", (fields) => fields.textContent || ""), /次回の確認目安.*AIの提案値/);
    assert(Number(await calendarPage.$eval('.work-record-dialog .follow-up-default-field input', (input) => input.value)) > 0, "AI work must provide a default follow-up day");
    await calendarPage.screenshot({ path: "/tmp/ina-work-record-desktop.png", fullPage: true });
    await calendarPage.click('.work-record-dialog > header .icon-button');
    await calendarPage.waitForFunction(() => !document.querySelector(".work-record-dialog"));
    await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  }
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const calendarOverflow = await calendarPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(calendarOverflow <= 1, `mobile calendar page must not overflow horizontally: ${calendarOverflow}px`);
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-mobile.png", fullPage: true });
  await calendarPage.close();

  const lockPage = await browser.newPage();
  await lockPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await lockPage.setRequestInterception(true);
  lockPage.on("request", async (request) => {
    if (!request.url().includes(`/local/api/fields/${fieldId}/plantings`)) {
      await request.continue();
      return;
    }
    try {
      const response = await fetch(request.url());
      const bundle = await response.json();
      const active = bundle.plantings.find((item) => item.status === "active");
      bundle.generation_tasks = active ? [{
        id: "ui-smoke-running-generation",
        field_id: fieldId,
        planting_id: active.id,
        kind: "regenerate",
        status: "running",
        updated_at: new Date().toISOString(),
      }] : [];
      await request.respond({ status: 200, contentType: "application/json", body: JSON.stringify(bundle) });
    } catch (error) {
      await request.abort("failed");
      browserErrors.push(String(error));
    }
  });
  await lockPage.goto(`${baseUrl}/fields/${fieldId}/calendar`, { waitUntil: "networkidle0" });
  await lockPage.waitForSelector('.calendar-drawer[data-calendar-edit-locked="true"] .calendar-edit-lock');
  assert.match(await lockPage.$eval(".calendar-edit-lock", (banner) => banner.textContent || ""), /作業編集を一時停止.*閲覧・検索・日付フィルタ/s);
  assert.equal(await lockPage.$eval(".calendar-action-list .calendar-section-heading button", (button) => button.disabled), true, "adding calendar work must be locked");
  assert.equal(await lockPage.$$eval(".calendar-kanban-card", (cards) => cards.every((card) => card.getAttribute("draggable") === "false")), true, "kanban dragging must be locked");
  assert.equal(await lockPage.$eval('.calendar-action-search input[type="search"]', (input) => input.disabled), false, "calendar search must remain available");
  await lockPage.screenshot({ path: "/tmp/ina-calendar-generation-edit-lock.png", fullPage: false });
  await lockPage.close();

  let reviewDecisionRequests = 0;
  let submittedReviewDecisions = [];
  let interceptedReviewBundle = null;
  const reviewPage = await browser.newPage();
  await reviewPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await reviewPage.setRequestInterception(true);
  reviewPage.on("request", async (request) => {
    try {
      if (request.method() === "POST" && request.url().includes("/calendar/regeneration-proposals/ui-smoke-review-generation/decisions")) {
        reviewDecisionRequests += 1;
        const payload = JSON.parse(request.postData() || "{}");
        submittedReviewDecisions = payload.decisions || [];
        assert(interceptedReviewBundle, "review bundle must be loaded before decisions are submitted");
        const nextBundle = structuredClone(interceptedReviewBundle);
        nextBundle.generation_tasks[0].status = "succeeded";
        nextBundle.generation_tasks[0].proposals = nextBundle.generation_tasks[0].proposals.map((proposal) => ({
          ...proposal,
          decision: submittedReviewDecisions.find((decision) => decision.proposal_id === proposal.id)?.decision || proposal.decision,
        }));
        await request.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ bundle: nextBundle }) });
        return;
      }
      if (!request.url().includes(`/local/api/fields/${fieldId}/plantings`)) {
        await request.continue();
        return;
      }
      const response = await fetch(request.url());
      const bundle = await response.json();
      const active = bundle.plantings.find((item) => item.status === "active");
      const currentAction = active ? bundle.calendars[active.id]?.actions?.[0] : null;
      assert(active && currentAction, "review smoke requires an active planting with a calendar action");
      bundle.generation_tasks = [{
        id: "ui-smoke-review-generation",
        field_id: fieldId,
        planting_id: active.id,
        kind: "regenerate",
        status: "awaiting_review",
        mode: "review",
        start_date: "2026-07-20",
        planning_notes: "",
        attempts: 1,
        error: "",
        created_at: new Date().toISOString(),
        started_at: new Date().toISOString(),
        finished_at: "",
        updated_at: new Date().toISOString(),
        proposals: [
          {
            id: "ui-smoke-update-proposal",
            change_type: "update",
            decision: "pending",
            existing_action_id: currentAction.id,
            title: "AIが提案した確認作業",
            before: currentAction,
            after: { ...currentAction, title: "AIが提案した確認作業", reason: "最新の栽培記録を反映するため" },
            decided_at: "",
          },
          {
            id: "ui-smoke-add-proposal",
            change_type: "add",
            decision: "pending",
            existing_action_id: "",
            title: "新しい生育確認",
            before: null,
            after: { ...currentAction, id: "ui-smoke-new-action", title: "新しい生育確認", source: "ai_replanned" },
            decided_at: "",
          },
        ],
      }];
      interceptedReviewBundle = structuredClone(bundle);
      await request.respond({ status: 200, contentType: "application/json", body: JSON.stringify(bundle) });
    } catch (error) {
      await request.abort("failed");
      browserErrors.push(String(error));
    }
  });
  await reviewPage.goto(`${baseUrl}/fields/${fieldId}/calendar`, { waitUntil: "networkidle0" });
  await selectCalendarWorkspace(reviewPage, "作物別の栽培計画");
  await reviewPage.waitForSelector(".calendar-regeneration-review");
  assert.equal(await reviewPage.$eval(".regeneration-commit-bar button", (button) => button.disabled), true, "batch apply must wait for every proposal selection");
  await reviewPage.click(".regeneration-proposal:nth-child(1) .proposal-actions button:last-child");
  await reviewPage.click(".regeneration-proposal:nth-child(2) .proposal-actions button:first-child");
  assert.equal(reviewDecisionRequests, 0, "proposal selection must not call the API");
  assert.equal(await reviewPage.$$(".proposal-actions button[aria-pressed=\"true\"]").then((items) => items.length), 2, "proposal choices must update immediately");
  assert.match(await reviewPage.$eval(".regeneration-review-counts", (counts) => counts.textContent || ""), /取り入れる 1件.*変更しない 1件.*未選択 0件/s);
  assert.equal(await reviewPage.$eval(".regeneration-commit-bar button", (button) => button.disabled), false, "batch apply must become available after all choices");
  await reviewPage.screenshot({ path: "/tmp/ina-calendar-regeneration-batch-review.png", fullPage: true });
  await reviewPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 150));
  const reviewOverflow = await reviewPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(reviewOverflow <= 1, `mobile regeneration review must not overflow horizontally: ${reviewOverflow}px`);
  await reviewPage.screenshot({ path: "/tmp/ina-calendar-regeneration-batch-review-mobile.png", fullPage: true });
  await reviewPage.click(".regeneration-commit-bar button");
  await reviewPage.waitForFunction(() => !document.querySelector(".calendar-regeneration-review"));
  assert.equal(reviewDecisionRequests, 1, "all proposal decisions must use one API request");
  assert.equal(submittedReviewDecisions.length, 2, "the batch request must include every pending proposal");
  await reviewPage.close();

  assert.match(await page.$eval("[data-field-tab='monitoring']", (tab) => tab.textContent || ""), /環境・設備/);
  await page.click("[data-field-tab='monitoring']");
  await page.waitForSelector("[data-tab-panel='monitoring']:not([hidden])");
  assert.equal(await page.$eval(".scope-device-settings", (link) => link.getAttribute("target")), "_blank");
  await page.screenshot({ path: "/tmp/ina-field-monitoring-desktop.png", fullPage: true });

  await page.click("[data-field-tab='cultivation']");
  await page.waitForSelector("[data-planting-form]");
  assert.match(await page.$eval("[data-tab-panel='cultivation']", (panel) => panel.textContent || ""), /年間カレンダーを開く/);
  assert.equal(await page.$eval(".planting-calendar-link", (link) => link.getAttribute("target")), "_blank");
  assert.match(await page.$eval("[data-tab-panel='cultivation']", (panel) => panel.textContent || ""), /直近の履歴/);
  await page.screenshot({ path: "/tmp/ina-field-cultivation-desktop.png", fullPage: true });

  await page.click("[data-field-tab='records']");
  await page.waitForSelector("[data-tab-panel='records']:not([hidden])");
  assert.match(await page.$eval("#record-image-dropzone", (zone) => zone.textContent || ""), /画像を選択・貼り付け.*最大5枚/s);
  await page.$eval("#field-record-form .record-extras", (details) => { details.open = true; });
  await page.$eval("#field-record-composer", (section) => section.scrollIntoView({ block: "start" }));
  await page.screenshot({ path: "/tmp/ina-field-record-image-paste.png", fullPage: false });
  assert(await page.$('input[aria-label="栽培記録を検索"]'), "the growing record history must provide API search");
  await page.type('input[aria-label="栽培記録を検索"]', "一致しない栽培記録");
  await page.waitForFunction(() => (
    document.querySelector("#record-history-count")?.textContent?.trim() === "0 / 0件"
    && document.querySelector("#record-history-status")?.textContent?.includes("一致する記録はありません")
  ));
  assert.match(await page.$eval("#record-history-status", (status) => status.textContent || ""), /一致する記録はありません/);
  await page.$eval('input[aria-label="栽培記録を検索"]', (input) => {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.waitForFunction(() => !document.querySelector("#record-history-status")?.textContent?.includes("検索しています"));
  await page.screenshot({ path: "/tmp/ina-field-record-search-desktop.png", fullPage: true });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `mobile page must not overflow horizontally: ${overflow}px`);
  await page.screenshot({ path: "/tmp/ina-field-cultivation-mobile.png", fullPage: true });

  await page.goto(`${baseUrl}/settings/ai`, { waitUntil: "networkidle0" });
  assert.equal(await page.$$eval("[data-ai-provider]", (providers) => providers.length), 2);
  await page.screenshot({ path: "/tmp/ina-ai-settings-mobile.png", fullPage: true });
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));

  process.stdout.write(JSON.stringify({
    tabs: 5,
    installationTreeInitiallyOpen: false,
    placementDeepLink: true,
    screenshots: [
      "/tmp/ina-field-todo-desktop.png",
      "/tmp/ina-agentic-watering-readiness.png",
      "/tmp/ina-agentic-watering-readiness-mobile.png",
      "/tmp/ina-agentic-human-readiness.png",
      "/tmp/ina-environment-target-direct.png",
      "/tmp/ina-care-profile-desktop.png",
      "/tmp/ina-calendar-regeneration-modes.png",
      "/tmp/ina-fertilizer-catalog-desktop.png",
      "/tmp/ina-fertilizer-catalog-add.png",
      "/tmp/ina-fertilizer-catalog-mobile.png",
      "/tmp/ina-fertilizer-preset-poultry.png",
      "/tmp/ina-fertilizer-entry-modal.png",
      "/tmp/ina-fertilizer-preset-poultry-mobile.png",
      "/tmp/ina-fertilizer-effect-desktop.png",
      "/tmp/ina-calendar-mobile.png",
      "/tmp/ina-calendar-generation-edit-lock.png",
      "/tmp/ina-calendar-regeneration-batch-review.png",
      "/tmp/ina-calendar-regeneration-batch-review-mobile.png",
      "/tmp/ina-calendar-planned-action.png",
      "/tmp/ina-calendar-action-journal-mobile.png",
      "/tmp/ina-calendar-action-journal-mobile-task.png",
      "/tmp/ina-calendar-edit-action-modal.png",
      "/tmp/ina-work-record-desktop.png",
      "/tmp/ina-field-monitoring-desktop.png",
      "/tmp/ina-field-cultivation-desktop.png",
      "/tmp/ina-field-record-image-paste.png",
      "/tmp/ina-field-record-search-desktop.png",
      "/tmp/ina-field-cultivation-mobile.png",
      "/tmp/ina-ai-settings-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}

async function replaceValue(targetPage, selector, value) {
  await targetPage.$eval(selector, (control, nextValue) => {
    const prototype = control instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, "value")?.set;
    setter?.call(control, nextValue);
    control.dispatchEvent(new Event("input", { bubbles: true }));
    control.dispatchEvent(new Event("change", { bubbles: true }));
    control.blur();
  }, value);
}
