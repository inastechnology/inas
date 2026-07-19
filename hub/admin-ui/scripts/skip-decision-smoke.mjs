import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39252";
const fieldId = "demo-strawberry-field";
const placementId = "skip-decision-smoke-pot";
const today = new Date().toISOString().slice(0, 10);

async function requestJson(path, options = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    ...options,
    headers: { Accept: "application/json", ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${response.status} ${JSON.stringify(body)}`);
  return body;
}

const layout = await requestJson(`/local/api/fields/${fieldId}/layout`);
const rootSpace = layout.spaces.find((space) => space.id === layout.root_space_id);
if (!rootSpace.placements.some((placement) => placement.id === placementId)) {
  rootSpace.placements.push({
    id: placementId,
    preset: "pot",
    name: "見送り確認鉢",
    x: 4,
    y: 4,
    width: 2,
    height: 2,
  });
  await requestJson(`/local/api/fields/${fieldId}/layout`, { method: "PUT", body: JSON.stringify(layout) });
}

let bundle = await requestJson(`/local/api/fields/${fieldId}/plantings`);
let planting = bundle.plantings.find((item) => item.status === "active" && item.placement_id === placementId);
if (!planting) {
  const created = await requestJson(`/local/api/fields/${fieldId}/plantings`, {
    method: "POST",
    body: JSON.stringify({
      space_id: layout.root_space_id,
      placement_id: placementId,
      crop_name: "ブルーベリー",
      cultivar: "見送り確認用",
      crop_category: "fruit_tree",
      tree_age_years: 3,
      planted_on: today,
      plant_count: 1,
      cultivation_method: "container",
      conditions: { environment: "屋外", soil_or_substrate: "酸性培養土", sunlight: "日なた" },
    }),
  });
  planting = created.planting;
}

for (let attempt = 0; attempt < 30; attempt += 1) {
  bundle = await requestJson(`/local/api/fields/${fieldId}/plantings`);
  if (bundle.calendars[planting.id]) break;
  await new Promise((resolve) => setTimeout(resolve, 200));
}
let calendar = bundle.calendars[planting.id];
assert(calendar, "calendar generation must complete");
let action = calendar.actions.find((item) => item.status === "planned");
if (!action) {
  action = await requestJson(`/local/api/plantings/${planting.id}/calendar/actions`, {
    method: "POST",
    body: JSON.stringify({ action_type: "observation", title: "見送り確認作業", window_start: today, window_end: today }),
  });
}

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });

try {
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields/${fieldId}/calendar?planting=${planting.id}`, { waitUntil: "networkidle0" });
  await page.click(`.calendar-kanban-card[data-action-id="${action.id}"]`);
  await page.waitForSelector(".calendar-action-detail-dialog .skip-button");
  await page.click(".calendar-action-detail-dialog .skip-button");
  await page.type(".skip-decision-form textarea[required]", "葉色と新梢は良好で、現在は作業不要と確認した");
  await page.type(".skip-decision-form textarea:not([required])", "期限切れの自動作業を現地確認した");
  await page.click('.skip-decision-form button[type="submit"]');
  await page.waitForSelector(".calendar-action-detail-dialog .skipped-badge");
  assert.match(await page.$eval(".skip-decision-record", (record) => record.textContent || ""), /現在は作業不要/);
  await page.screenshot({ path: "/tmp/ina-skip-decision-smoke.png", fullPage: true });

  bundle = await requestJson(`/local/api/fields/${fieldId}/plantings`);
  calendar = bundle.calendars[planting.id];
  const stored = calendar.actions.find((item) => item.id === action.id);
  assert.equal(stored.status, "skipped");
  assert.equal(stored.skip_decision.reason_code, "generated_in_error");
  assert(!bundle.suggestions.some((item) => item.action.id === action.id), "skipped work must leave suggestions");
  const records = await requestJson(`/local/api/fields/${fieldId}/records?q=${encodeURIComponent("期限切れの自動作業")}`);
  assert(records.items.some((item) => item.source === "event"), "skip decision must appear in field history");
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));
  process.stdout.write(`${JSON.stringify({ plantingId: planting.id, actionId: action.id, status: stored.status })}\n`);
} finally {
  await browser.close();
}
