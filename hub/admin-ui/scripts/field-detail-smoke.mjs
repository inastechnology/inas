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
  assert.equal(await calendarPage.$$(".installation-app").then((items) => items.length), 0, "calendar page must not mount the installation editor");
  assert.match(await calendarPage.$eval(".calendar-workspace-tabs button.active", (button) => button.textContent || ""), /圃場の作業/);
  assert.match(await calendarPage.$eval(".calendar-work-scope", (scope) => scope.textContent || ""), /圃場のすべての作物/, "the work board must offer all crops in the field");
  assert.equal(await calendarPage.$$(".calendar-section-heading small").then((items) => items.filter((item) => /^r\d+/.test(item.textContent || "")).length), 0, "internal calendar revisions must stay hidden");
  await selectCalendarWorkspace(calendarPage, "作物別の栽培計画");
  await calendarPage.evaluate(() => { const shell = document.querySelector('.calendar-page-shell'); if (shell instanceof HTMLElement) shell.scrollTop = 0; });
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-crop-plan-desktop.png", fullPage: true });
  await calendarPage.click(".calendar-generation .calendar-section-heading button");
  await calendarPage.waitForSelector('.generation-mode-options input[value="review"]:checked');
  assert.equal(await calendarPage.$$(".generation-mode-options label").then((items) => items.length), 2, "regeneration must offer review and automatic modes");
  assert.match(await calendarPage.$eval(".calendar-generation form", (form) => form.textContent || ""), /現在の.*件の作業.*重複させません/s);
  await calendarPage.$eval(".calendar-generation", (section) => section.scrollIntoView({ block: "start" }));
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-regeneration-modes.png", fullPage: false });
  await calendarPage.click('.calendar-generation .form-actions button[type="button"]');
  await calendarPage.waitForFunction(() => !document.querySelector(".calendar-generation form"));
  assert.equal(await calendarPage.$$(".gantt-period-controls").then((items) => items.length), 1);
  assert.match(await calendarPage.$eval(".fertilizer-effect-panel", (panel) => panel.textContent || ""), /培地の施肥と残存肥効/);
  const fertilizerCount = await calendarPage.$$(".fertilizer-history-list article").then((items) => items.length);
  await calendarPage.$eval(".fertilizer-effect-panel .calendar-section-heading button", (button) => button.click());
  await calendarPage.waitForSelector("[data-fertilizer-form]");
  assert.match(await calendarPage.$eval("[data-fertilizer-form]", (form) => form.textContent || ""), /製品kgと養分kgを分けて計算/);
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="amount_kg"]', "20");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="n_percent"]', "2");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="p2o5_percent"]', "1");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="k2o_percent"]', "1.5");
  await replaceValue(calendarPage, '[data-fertilizer-form] input[name="mgo_percent"]', "0.5");
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
  assert.match(await calendarPage.$eval('.calendar-action-create-dialog', (dialog) => dialog.textContent || ""), /対象の作物.*詳しい作業内容・画像/);
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
  if (await calendarPage.$(".calendar-action-detail-dialog .calendar-action.planned")) {
    assert.equal(await calendarPage.$(".calendar-action-detail-dialog .complete-button"), null, "planned work must not offer completion recording");
    assert(await calendarPage.$(".calendar-action-detail-dialog .start-button"), "planned work must offer a start action");
    await calendarPage.click(".calendar-action-detail-dialog .action-edit-button");
    await calendarPage.waitForSelector(".action-edit-dialog .rich-action-content");
    assert.match(await calendarPage.$eval(".action-edit-dialog > header", (header) => header.textContent || ""), /実績入力とは別に編集/);
    await calendarPage.screenshot({ path: "/tmp/ina-calendar-edit-action-modal.png", fullPage: true });
    await calendarPage.click(".action-edit-dialog > header .icon-button");
    const deleteConfirmation = new Promise((resolve) => calendarPage.once("dialog", async (dialog) => { assert.match(dialog.message(), /元に戻せません/); await dialog.dismiss(); resolve(); }));
    await calendarPage.click(".calendar-action-detail-dialog .action-icon-button.danger");
    await deleteConfirmation;
    await calendarPage.screenshot({ path: "/tmp/ina-calendar-planned-action.png", fullPage: true });
  }
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /開始条件/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /見送り/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-guidance", (panel) => panel.textContent || ""), /完了確認/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-method-detail[open]", (panel) => panel.textContent || ""), /手順/);
  assert.match(await calendarPage.$eval(".calendar-action-detail-dialog .work-method-detail[open]", (panel) => panel.textContent || ""), /頻度/);
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
    await calendarPage.waitForSelector(".work-detail-fields");
    const workMethodSelect = ".work-detail-fields .searchable-select";
    assert.equal(await calendarPage.$(`${workMethodSelect} input[type="search"]`), null, "work method search must be inside the closed dropdown");
    await calendarPage.click(`${workMethodSelect} .searchable-select-control`);
    await calendarPage.waitForSelector(`${workMethodSelect} input[type="search"]`);
    await calendarPage.type(`${workMethodSelect} input[type="search"]`, "一致しない方法");
    assert(await calendarPage.$(`${workMethodSelect} [data-searchable-option][data-value="custom"]`), "custom method must remain available while filtering");
    await calendarPage.click(`${workMethodSelect} [data-searchable-option][data-value="custom"]`);
    await calendarPage.select('.work-detail-fields select', "material_application");
    assert.match(await calendarPage.$eval(".work-detail-fields", (fields) => fields.textContent || ""), /実施内容/);
    assert.match(await calendarPage.$eval(".work-detail-fields", (fields) => fields.textContent || ""), /使用した資材・製品/);
    assert.match(await calendarPage.$eval(".work-detail-fields", (fields) => fields.textContent || ""), /実際の使用量・希釈・処理時間/);
    assert.match(await calendarPage.$eval(".work-detail-fields", (fields) => fields.textContent || ""), /次回の確認目安.*AIの提案値/);
    assert(Number(await calendarPage.$eval('.follow-up-default-field input', (input) => input.value)) > 0, "AI work must provide a default follow-up day");
    await calendarPage.screenshot({ path: "/tmp/ina-work-record-desktop.png", fullPage: true });
    await calendarPage.click('.work-record-form button[type="button"]');
    await calendarPage.click(".calendar-action-detail-dialog > header .icon-button");
  }
  await calendarPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  const calendarOverflow = await calendarPage.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(calendarOverflow <= 1, `mobile calendar page must not overflow horizontally: ${calendarOverflow}px`);
  await calendarPage.screenshot({ path: "/tmp/ina-calendar-mobile.png", fullPage: true });
  await calendarPage.close();
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
      "/tmp/ina-environment-target-direct.png",
      "/tmp/ina-care-profile-desktop.png",
      "/tmp/ina-calendar-regeneration-modes.png",
      "/tmp/ina-fertilizer-effect-desktop.png",
      "/tmp/ina-calendar-mobile.png",
      "/tmp/ina-calendar-planned-action.png",
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
