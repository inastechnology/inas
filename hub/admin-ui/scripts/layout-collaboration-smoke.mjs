import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const fieldId = "demo-strawberry-field";
const apiUrl = `${baseUrl}/local/api/fields/${fieldId}/layout`;
const original = await fetchJson(apiUrl);
const fixtureSpace = original.spaces.find((space) => space.placements.length > 0);
const originalPlacement = fixtureSpace?.placements[0];
assert(fixtureSpace && originalPlacement, "the collaboration fixture placement must exist");
const placementId = originalPlacement.id;
const layoutUrl = `${baseUrl}/fields/${fieldId}/layout?space=${encodeURIComponent(fixtureSpace.id)}&placement=${encodeURIComponent(placementId)}`;

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const first = await browser.newPage();
const second = await browser.newPage();
const browserErrors = [];
const collaborationRequests = new Map([[first, []], [second, []]]);
for (const page of [first, second]) {
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  page.on("request", (request) => {
    if (!request.url().endsWith("/layout/collaboration") || request.method() !== "POST") return;
    collaborationRequests.get(page).push(JSON.parse(request.postData() || "{}"));
  });
  await page.setViewport({ width: 1280, height: 820, deviceScaleFactor: 1 });
}

const localMemo = `共同編集メモ-${Date.now()}`;
const remoteName = `${originalPlacement.name}-共同編集確認`;

try {
  process.stdout.write("opening two editor tabs\n");
  await first.goto(layoutUrl, { waitUntil: "networkidle0" });
  await second.goto(layoutUrl, { waitUntil: "networkidle0" });
  try {
    await Promise.all([
      first.waitForFunction(() => {
        const text = document.querySelector(".collaboration-presence-label")?.textContent || "";
        const screenCount = Number(text.match(/・(\d+)画面/)?.[1] || "0");
        return Number.parseInt(text, 10) >= 2 || screenCount >= 2;
      }, { polling: 200, timeout: 15_000 }),
      second.waitForFunction(() => {
        const text = document.querySelector(".collaboration-presence-label")?.textContent || "";
        const screenCount = Number(text.match(/・(\d+)画面/)?.[1] || "0");
        return Number.parseInt(text, 10) >= 2 || screenCount >= 2;
      }, { polling: 200, timeout: 15_000 }),
    ]);
  } catch (error) {
    const diagnostics = await Promise.all([first, second].map(async (page) => ({
      label: await page.$eval(".collaboration-presence-label", (element) => element.textContent || ""),
      requests: collaborationRequests.get(page),
    })));
    throw new Error(`presence did not converge: ${JSON.stringify(diagnostics)}`, { cause: error });
  }
  process.stdout.write("presence connected\n");

  await first.waitForFunction(
    (expectedName) => (document.querySelector(".canvas-connection-summary")?.textContent || "").includes(`が${expectedName}を選択中`),
    { polling: 200, timeout: 10_000 },
    originalPlacement.name,
  );
  const selectionSummary = await first.$eval(".canvas-connection-summary", (element) => element.textContent || "");
  assert.match(selectionSummary, new RegExp(`が${escapeRegExp(originalPlacement.name)}を選択中`));
  process.stdout.write("remote selection visible\n");

  const inspectorDiagnostic = await second.evaluate(() => ({
    text: document.querySelector(".inspector-panel")?.textContent || "",
    textareas: document.querySelectorAll(".inspector-content textarea").length,
  }));
  assert(inspectorDiagnostic.textareas > 0, `placement memo was not rendered: ${inspectorDiagnostic.text}`);
  await replaceValue(second, ".inspector-content textarea", localMemo);
  process.stdout.write("second editor changed memo\n");
  assert.match(await second.$eval(".save-state", (element) => element.textContent || ""), /未保存/);
  await replaceValue(first, ".inspector-content > label:first-of-type input", remoteName);
  process.stdout.write("first editor changed name\n");
  await first.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("未保存"), { polling: 100, timeout: 5_000 });
  assert.equal(await first.$eval(".save-button", (button) => button.disabled), false, "first editor save must be enabled");
  const firstSaveResponse = first.waitForResponse(
    (response) => response.url() === apiUrl && response.request().method() === "PUT",
    { timeout: 8_000 },
  );
  await first.$eval(".save-button", (button) => button.click());
  assert.equal((await firstSaveResponse).ok(), true, "first editor save must succeed");
  await first.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"), { polling: 100, timeout: 5_000 });
  process.stdout.write("first editor saved\n");

  await second.waitForFunction(
    (expected) => document.querySelector(".inspector-content > label:first-of-type input")?.value === expected,
    { polling: 200, timeout: 8_000 },
    remoteName,
  );
  assert.equal(await second.$eval(".inspector-content textarea", (input) => input.value), localMemo);
  assert.match(await second.$eval(".collaboration-notice", (element) => element.textContent || ""), /自動統合/);
  assert.equal(await second.$(".layout-conflict-dialog"), null, "separate edits must not open the conflict dialog");
  process.stdout.write("second editor auto-merged\n");

  const secondSaveResponse = second.waitForResponse(
    (response) => response.url() === apiUrl && response.request().method() === "PUT",
    { timeout: 8_000 },
  );
  await second.$eval(".save-button", (button) => button.click());
  assert.equal((await secondSaveResponse).ok(), true, "second editor save must succeed");
  await second.waitForFunction(() => document.querySelector(".save-state")?.textContent?.includes("保存済み"), { polling: 100, timeout: 5_000 });
  const saved = await fetchJson(apiUrl);
  const savedPlacement = findPlacement(saved, placementId);
  assert.equal(savedPlacement?.name, remoteName);
  assert.equal(savedPlacement?.memo, localMemo);
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));
  await second.screenshot({ path: "/tmp/ina-layout-collaboration.png", fullPage: false });
  await second.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 300));
  const presenceBounds = await second.$eval(".collaboration-presence > summary", (element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewportWidth: window.innerWidth };
  });
  assert(presenceBounds.left >= 0 && presenceBounds.right <= presenceBounds.viewportWidth, "collaboration status must stay inside the mobile viewport");
  await second.$eval(".collaboration-presence", (details) => { details.open = true; });
  const popoverBounds = await second.$eval(".collaboration-presence-popover", (element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewportWidth: window.innerWidth };
  });
  assert(popoverBounds.left >= 0 && popoverBounds.right <= popoverBounds.viewportWidth, "participant list must stay inside the mobile viewport");
  await second.screenshot({ path: "/tmp/ina-layout-collaboration-mobile.png", fullPage: false });
  process.stdout.write(JSON.stringify({
    participants: 2,
    revision: saved.revision,
    screenshots: ["/tmp/ina-layout-collaboration.png", "/tmp/ina-layout-collaboration-mobile.png"],
  }, null, 2) + "\n");
} finally {
  const latest = await fetchJson(apiUrl);
  await fetchJson(apiUrl, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...original, revision: latest.revision }),
  });
  const browserProcess = browser.process();
  const closed = await Promise.race([
    browser.close().then(() => true),
    new Promise((resolve) => setTimeout(() => resolve(false), 4_000)),
  ]);
  if (!closed && browserProcess && !browserProcess.killed) browserProcess.kill("SIGTERM");
}

function findPlacement(layout, id) {
  return layout.spaces.flatMap((space) => space.placements).find((placement) => placement.id === id);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

async function replaceValue(page, selector, value) {
  await page.waitForSelector(selector);
  await page.$eval(selector, (input) => {
    input.focus();
    input.select();
  });
  await page.type(selector, value);
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request failed: ${response.status}`);
  return body;
}
