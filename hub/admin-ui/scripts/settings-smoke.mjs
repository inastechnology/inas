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
let aiTestScenario = "";
await page.setRequestInterception(true);
page.on("request", (request) => {
  if (request.url().endsWith("/local/api/settings/ai/test") && aiTestScenario) {
    if (aiTestScenario === "success") {
      request.respond({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          model: "gpt-5.6-luna",
          response: "OK",
          parameters: { temperature_mode: "auto", temperature: null, reasoning_effort: "default" },
          adjustments: [{ parameter: "temperature", title: "出力の揺らぎはモデルに任せました", message: "非対応の温度を省略して再接続しました。" }],
        }),
      });
      return;
    }
    request.respond({
      status: 422,
      contentType: "application/json",
      body: JSON.stringify({
        error: "選択したモデルは、指定した温度を受け付けませんでした。",
        diagnostic: {
          title: "出力の揺らぎ設定がモデルに対応していません",
          summary: "選択したモデルは、指定した温度を受け付けませんでした。",
          suggestions: ["出力の揺らぎを「自動調整（おすすめ）」に変更します。", "設定を保存してから、もう一度接続を確認します。"],
          category: "unsupported_parameter",
          code: "unsupported_value",
          parameter: "temperature",
          upstream_status: 400,
          technical_detail: "Unsupported value for temperature",
        },
      }),
    });
    return;
  }
  request.continue();
});
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

try {
  await page.setViewport({ width: 1280, height: 860, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields`, { waitUntil: "networkidle0" });
  assert(await page.$('a[href="/preferences"]'));
  assert(await page.$('a[href="/settings"]'));
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle0" }), page.click('a[href="/preferences"]')]);
  assert.equal(await page.$eval("h1", (heading) => heading.textContent?.trim()), "個人設定");
  assert(await page.$("#preference-search"));
  assert.equal(await page.$('select[name="locale"]'), null);
  assert(await page.$('select[name="cultivation_experience"]'));
  assert.equal(await page.$$eval('select[name="cultivation_experience"] option', (options) => options.length), 3);
  assert.match(await page.$eval('select[name="cultivation_experience"]', (select) => select.textContent || ""), /初心者.*標準.*プロ/s);
  assert.equal(await page.$eval('#preference-form button[type="submit"]', (button) => button.disabled), true, "unchanged personal settings must not be saved");
  await page.type("#preference-search", "日付");
  await page.waitForFunction(() => document.querySelectorAll('.setting-row:not([hidden])').length === 1);
  await page.screenshot({ path: "/tmp/ina-personal-settings-filter.png", fullPage: true });
  await page.$eval("#preference-search", (input) => {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.$eval('select[name="date_format"]', (select) => {
    select.value = select.value === "yyyy-MM-dd" ? "yyyy/MM/dd" : "yyyy-MM-dd";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  assert.equal(await page.$eval('#preference-form button[type="submit"]', (button) => button.disabled), false, "changed personal settings must be saveable");
  await page.evaluate(async () => {
    const currentResponse = await fetch("/local/api/me/preferences", { headers: { Accept: "application/json" } });
    const current = await currentResponse.json();
    const response = await fetch("/local/api/me/preferences", {
      method: "PATCH",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        ...current.preferences,
        timezone: current.preferences.timezone === "UTC" ? "Asia/Tokyo" : "UTC",
      }),
    });
    if (!response.ok) throw new Error(`concurrent preference update failed: ${response.status}`);
  });
  await page.click('#preference-form button[type="submit"]');
  await page.waitForSelector("#conflict-dialog[open]");
  consumeExpectedConflict(browserErrors, "personal preferences");
  await page.screenshot({ path: "/tmp/ina-personal-settings-conflict.png", fullPage: true });
  await page.click("#retry-local");
  await page.waitForFunction(() => document.querySelector("#save-state")?.textContent?.includes("保存しました"));

  await page.goto(`${baseUrl}/fields`, { waitUntil: "networkidle0" });
  await Promise.all([page.waitForNavigation({ waitUntil: "networkidle0" }), page.click('a[href="/settings"]')]);
  assert.equal(await page.$eval("h1", (heading) => heading.textContent?.trim()), "アプリ設定");
  assert(await page.$("#settings-search"));
  assert.equal(await page.$('select[name="default_language"]'), null);
  assert(await page.$('input[name="text_analyze_model"]'));
  assert(await page.$('select[name="text_analyze_temperature_mode"]'));
  assert(await page.$('input[name="text_analyze_temperature"]'));
  assert(await page.$('select[name="text_analyze_reasoning_effort"]'));
  assert(await page.$("#ai-test-dialog"));
  assert(await page.$('input[type="password"][name="text_analyze_api_key"]'));
  assert(await page.$('input[type="password"][name="image_analyze_api_key"]'));
  assert(await page.$('textarea[name="plant_calendar_prompt_template"]'));
  assert.match(
    await page.$eval('textarea[name="plant_calendar_prompt_template"]', (textarea) => textarea.value),
    /\{default_instructions\}.*\{context_json\}.*\{guidance_json\}/s,
  );
  assert.equal(await page.$eval('input[name="text_analyze_api_key"]', (input) => input.value), "");
  assert.equal(await page.$eval('input[name="image_analyze_api_key"]', (input) => input.value), "");
  assert(await page.$('input[name="post_schedule_start"]'));
  assert(await page.$('select[name="camera_id"]'));
  assert(await page.$('select[name="camera_id"] + .static-searchable-select'), "camera selector must use the shared searchable dropdown");
  assert.equal(await page.$eval('select[name="camera_id"] + .static-searchable-select input[type="search"]', (input) => input.offsetParent === null), true, "camera search must stay hidden inside the closed dropdown");
  await page.click('select[name="camera_id"] + .static-searchable-select .searchable-select-control');
  await page.waitForSelector('select[name="camera_id"] + .static-searchable-select input[type="search"]', { visible: true });
  await page.keyboard.press("Escape");
  assert(await page.$('textarea[name="plant_position_prompt"]'));
  assert.equal(await page.$eval('#ai-settings-form button[type="submit"]', (button) => button.disabled), true, "unchanged app settings must not be saved");

  const textProvider = '[data-ai-provider="text"]';
  await page.click(`${textProvider} .model-advanced summary`);
  await page.select(`${textProvider} select[name="text_analyze_temperature_mode"]`, "custom");
  await page.$eval(`${textProvider} input[name="text_analyze_temperature"]`, (input) => {
    input.value = "0.2";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(await page.$eval(`${textProvider} [data-temperature-panel]`, (panel) => panel.hidden), false);
  assert.equal(await page.$eval(`${textProvider} [data-temperature-output]`, (output) => output.textContent), "0.2");
  await page.screenshot({ path: "/tmp/ina-ai-model-advanced.png", fullPage: true });

  aiTestScenario = "success";
  await page.$eval(`${textProvider} [data-test-ai]`, (button) => { button.disabled = false; });
  await page.click(`${textProvider} [data-test-ai]`);
  await page.waitForFunction(() => document.querySelector("#ai-test-dialog")?.hidden === false);
  assert.match(await page.$eval("#ai-test-dialog-title", (element) => element.textContent || ""), /接続できました/);
  await page.screenshot({ path: "/tmp/ina-ai-model-success.png", fullPage: true });
  await page.click("#ai-test-dialog [data-ai-dialog-close]");

  aiTestScenario = "error";
  await page.click(`${textProvider} [data-test-ai]`);
  await page.waitForFunction(() => document.querySelector("#ai-test-dialog")?.hidden === false);
  consumeExpectedHttpError(browserErrors, "422", "AI diagnostic");
  assert.match(await page.$eval("#ai-test-dialog-title", (element) => element.textContent || ""), /対応していません/);
  assert.match(await page.$eval("#ai-test-dialog-suggestions", (element) => element.textContent || ""), /自動調整/);
  await page.screenshot({ path: "/tmp/ina-ai-model-error.png", fullPage: true });
  await page.click("#ai-test-dialog [data-ai-dialog-close]");
  aiTestScenario = "";

  await page.type("#settings-search", "Turso");
  await page.waitForFunction(() => document.querySelector('[data-settings-section="ai"]')?.hidden === true);
  assert.equal(await page.$eval('[data-settings-section="system"]', (section) => section.hidden), false);
  assert.equal(await page.$eval('[data-settings-section="ai"]', (section) => section.hidden), true);
  assert.equal(await page.$eval('[data-settings-section="instagram"]', (section) => section.hidden), true);
  await page.screenshot({ path: "/tmp/ina-app-settings-filter.png", fullPage: true });

  await page.$eval("#settings-search", (input) => {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.$eval('input[name="text_analyze_model"]', (input) => {
    input.value = `${input.value || "text-model"}-smoke`;
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  assert.equal(await page.$eval('#ai-settings-form button[type="submit"]', (button) => button.disabled), false, "changed app settings must be saveable");
  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.click('#ai button[type="submit"]'),
  ]);
  assert.match(page.url(), /\/settings\?section=ai&saved=1$/);
  assert.match(await page.$eval('[role="status"]', (notice) => notice.textContent || ""), /保存しました/);
  await page.screenshot({ path: "/tmp/ina-app-settings.png", fullPage: true });

  await page.goto(`${baseUrl}/settings/ai`, { waitUntil: "networkidle0" });
  assert.match(page.url(), /\/settings\?section=ai$/);

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/settings`, { waitUntil: "networkidle0" });
  await page.click('[data-ai-provider="text"] .model-advanced summary');
  const bounds = await page.$eval(".settings-content", (element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewport: window.innerWidth };
  });
  assert(bounds.left >= 0 && bounds.right <= bounds.viewport, "settings content must fit the mobile viewport");
  await page.screenshot({ path: "/tmp/ina-app-settings-mobile.png", fullPage: true });
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));

  process.stdout.write(
    JSON.stringify({ screenshots: ["/tmp/ina-personal-settings-filter.png", "/tmp/ina-personal-settings-conflict.png", "/tmp/ina-ai-model-advanced.png", "/tmp/ina-ai-model-success.png", "/tmp/ina-ai-model-error.png", "/tmp/ina-app-settings.png", "/tmp/ina-app-settings-filter.png", "/tmp/ina-app-settings-mobile.png"] }, null, 2) + "\n",
  );
} finally {
  await browser.close();
}

function consumeExpectedConflict(errors, label) {
  const index = errors.findIndex((message) => message.includes("409 (CONFLICT)"));
  assert.notEqual(index, -1, `${label} must produce an HTTP 409 before merge`);
  errors.splice(index, 1);
}

function consumeExpectedHttpError(errors, status, label) {
  const index = errors.findIndex((message) => message.includes(status));
  assert.notEqual(index, -1, `${label} must produce the expected HTTP ${status}`);
  errors.splice(index, 1);
}
