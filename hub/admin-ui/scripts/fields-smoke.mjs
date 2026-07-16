import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const fieldName = `ブラウザ確認圃場-${Date.now()}`;
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
  await page.setViewport({ width: 1280, height: 860, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle0" });
  assert.match(await page.$eval("h1", (heading) => heading.textContent || ""), /圃場を選択/);
  assert.equal(await page.$('a[href="/mqtt-devices"]'), null);
  assert.equal(await page.$(".device-row"), null);
  await page.screenshot({ path: "/tmp/ina-field-selector-top.png", fullPage: true });

  await page.goto(`${baseUrl}/fields`, { waitUntil: "networkidle0" });
  await page.waitForSelector("#open-field-create");
  assert.equal(await page.$('form input[name="device_ids"]'), null);
  assert.equal(await page.$('form input[name="crop"]'), null);
  await page.screenshot({ path: "/tmp/ina-fields-list.png", fullPage: true });

  await page.click("#open-field-create");
  await page.waitForFunction(() => document.querySelector("#field-create-dialog")?.open === true);
  await page.type('#field-create-dialog input[name="name"]', fieldName);
  await chooseStaticSearchableOption(page, '#field-create-dialog select[name="prefecture"]', "長野県", "長野");
  await page.type('#field-create-dialog input[name="municipality"]', "伊那市");
  await page.select('#field-create-dialog select[name="environment_type"]', "outdoor");
  await page.type('#field-create-dialog input[name="locality"]', "西箕輪");
  await page.screenshot({ path: "/tmp/ina-field-create-modal.png" });

  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.click('#field-create-dialog button[type="submit"]'),
  ]);
  assert.match(page.url(), /\/fields\/[^/]+$/);
  assert(await page.$('select[name="prefecture"]'));
  assert(await page.$('input[name="municipality"]'));
  assert.equal(await page.$('select[name="stage"]'), null);
  assert.equal(await page.$('select[name="cultivation_method"]'), null);
  assert.equal(await page.$('input[name="crop"]'), null);
  assert(await page.$('select[name="prefecture"] + .static-searchable-select'), "field prefecture must use the shared searchable dropdown");

  const fields = await fetchJson(`${baseUrl}/local/api/fields`);
  const field = fields.items.find((item) => item.name === fieldName);
  assert(field, "created field must be returned by API");
  assert.equal(field.location.prefecture, "長野県");
  assert.equal(field.location.municipality, "伊那市");
  assert.equal(field.location.environment_type, "outdoor");
  assert.equal(field.crop, "");
  assert.deepEqual(field.device_ids, []);

  await page.click('[data-field-tab="records"]');
  assert.equal(await page.$("#field-status-dashboard .range-card"), null);
  assert.equal(await page.$("#record-automatic-section:not([hidden])"), null);
  assert(await page.$("#record-target-select + .static-searchable-select"), "record target must use the shared searchable dropdown");
  await page.click("#record-target-select + .static-searchable-select .searchable-select-control");
  await page.waitForSelector("#record-target-select + .static-searchable-select input[type=\"search\"]", { visible: true });
  await page.keyboard.press("Escape");
  await page.click("#record-item-search-open");
  await page.type("#record-item-query", "EC");
  await page.waitForFunction(() => Array.from(document.querySelectorAll(".record-search-item strong")).some((item) => item.textContent === "EC"));
  await page.screenshot({ path: "/tmp/ina-device-free-record-search.png" });
  await page.evaluate(() => {
    const row = Array.from(document.querySelectorAll(".record-search-item")).find((item) => item.querySelector("strong")?.textContent === "EC");
    row?.querySelector("button")?.click();
  });
  await page.click("[data-record-item-dialog-close]");
  await page.waitForSelector('[data-record-value-key="soil_ec_us_cm"]');
  await page.click('[data-record-value-key="soil_ec_us_cm"] .remove-record-item');
  assert.equal(await page.$('[data-record-value-key="soil_ec_us_cm"]'), null);
  await page.click('#recent-record-item-list [data-add-record-item="soil_ec_us_cm"]');
  await page.type('[data-record-value-key="soil_ec_us_cm"] input[name="record_item_value"]', "850");

  await page.click("#record-item-search-open");
  await page.$eval("#record-item-query", (input) => {
    input.value = "";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.type("#record-item-query", "潅水時間");
  await page.waitForFunction(() => Array.from(document.querySelectorAll(".record-search-item strong")).some((item) => item.textContent === "潅水時間"));
  await page.evaluate(() => {
    const row = Array.from(document.querySelectorAll(".record-search-item")).find((item) => item.querySelector("strong")?.textContent === "潅水時間");
    row?.querySelector("button")?.click();
  });
  await page.click("[data-record-item-dialog-close]");
  await page.type('[data-record-value-key="watering_duration_min"] input[name="record_item_value"]', "15");
  await page.screenshot({ path: "/tmp/ina-device-free-record-composer.png", fullPage: true });

  await Promise.all([
    page.waitForNavigation({ waitUntil: "networkidle0" }),
    page.click('#field-record-form button[type="submit"]'),
  ]);
  await page.waitForSelector('#recent-record-item-list [data-add-record-item="soil_ec_us_cm"]');
  await page.click(".calendar-day.today");
  await page.waitForSelector("#record-day-modal:not([hidden])");
  const manualRecord = await page.evaluate(() => ({
    values: Array.from(document.querySelectorAll("#record-day-body .day-record-value")).map((item) => item.textContent?.trim()),
    automaticCount: document.querySelectorAll("#record-day-body .day-measurement").length,
  }));
  assert(manualRecord.values.some((value) => value?.includes("EC 850uS/cm")));
  assert(manualRecord.values.some((value) => value?.includes("潅水時間 15分")));
  assert.equal(manualRecord.automaticCount, 0);
  await page.screenshot({ path: "/tmp/ina-device-free-record-day.png" });
  await page.click("[data-record-modal-close]");

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields`, { waitUntil: "networkidle0" });
  await page.click("#open-field-create");
  await page.waitForFunction(() => document.querySelector("#field-create-dialog")?.open === true);
  const dialogWidth = await page.$eval("#field-create-dialog", (dialog) => dialog.getBoundingClientRect().width);
  assert(dialogWidth <= 390, "field creation dialog must fit the mobile viewport");
  await page.screenshot({ path: "/tmp/ina-field-create-modal-mobile.png" });
  await page.click("#close-field-create");
  await page.goto(`${baseUrl}/fields/${field.id}#records`, { waitUntil: "networkidle0" });
  await page.click("#record-item-search-open");
  const recordDialog = await page.$eval(".record-item-dialog", (dialog) => {
    const rect = dialog.getBoundingClientRect();
    return { width: rect.width, height: rect.height, viewportWidth: window.innerWidth, viewportHeight: window.innerHeight };
  });
  assert(recordDialog.width <= recordDialog.viewportWidth);
  assert(recordDialog.height <= recordDialog.viewportHeight);
  await page.screenshot({ path: "/tmp/ina-device-free-record-search-mobile.png" });
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));

  process.stdout.write(
    JSON.stringify(
      {
        fieldId: field.id,
        location: `${field.location.prefecture}${field.location.municipality} ${field.location.locality}`,
        environment: field.location.environment_type,
        screenshots: [
          "/tmp/ina-field-selector-top.png",
          "/tmp/ina-fields-list.png",
          "/tmp/ina-field-create-modal.png",
          "/tmp/ina-field-create-modal-mobile.png",
          "/tmp/ina-device-free-record-composer.png",
          "/tmp/ina-device-free-record-day.png",
          "/tmp/ina-device-free-record-search.png",
          "/tmp/ina-device-free-record-search-mobile.png",
        ],
      },
      null,
      2,
    ) + "\n",
  );
} finally {
  await browser.close();
}

async function fetchJson(url) {
  const response = await fetch(url);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request failed: ${response.status}`);
  return body;
}

async function chooseStaticSearchableOption(page, selectSelector, value, query = "") {
  const rootSelector = `${selectSelector} + .static-searchable-select`;
  assert(await page.$(rootSelector), `searchable select was not initialized: ${selectSelector}`);
  assert.equal(await page.$eval(`${rootSelector} input[type="search"]`, (input) => input.offsetParent === null), true, "search field must stay hidden inside the closed dropdown");
  await page.click(`${rootSelector} .searchable-select-control`);
  await page.waitForSelector(`${rootSelector} input[type="search"]`, { visible: true });
  if (query) await page.type(`${rootSelector} input[type="search"]`, query);
  await page.waitForSelector(`${rootSelector} [data-searchable-option][data-value="${value}"]`);
  await page.click(`${rootSelector} [data-searchable-option][data-value="${value}"]`);
  assert.equal(await page.$eval(selectSelector, (select) => select.value), value);
}
