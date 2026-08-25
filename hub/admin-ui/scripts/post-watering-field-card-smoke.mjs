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
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

try {
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  const response = await page.goto(`${baseUrl}/fields/${fieldId}#monitoring`, { waitUntil: "networkidle0" });
  assert.equal(response.status(), 200);
  await page.waitForSelector("#post-watering-notification-conditions:not([hidden])");
  assert.equal(await page.$eval('[data-field-tab="monitoring"]', (tab) => tab.getAttribute("aria-selected")), "true");
  assert.match(await page.$eval("#post-watering-notification-conditions", (section) => section.innerText || ""), /潅水後の水分チェック/);
  const fieldCardCount = await page.$$eval("[data-post-watering-condition-card]", (cards) => cards.length);
  assert(fieldCardCount > 0, "the demo field must list watering condition cards");
  const setupHref = await page.$eval("[data-post-watering-condition-card] .condition-card-action", (link) => link.getAttribute("href") || "");
  assert.match(setupHref, /watering_device_id=/);
  assert.match(setupHref, new RegExp(`field_id=${fieldId}`));
  await page.screenshot({ path: "/tmp/ina-field-notification-conditions-desktop.png", fullPage: true });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 150));
  const bounds = await page.$eval("#post-watering-notification-conditions", (section) => ({
    scrollWidth: section.scrollWidth,
    clientWidth: section.clientWidth,
  }));
  assert(bounds.scrollWidth <= bounds.clientWidth, `field notification condition cards must not overflow on mobile: ${bounds.scrollWidth}px > ${bounds.clientWidth}px`);
  await page.screenshot({ path: "/tmp/ina-field-notification-conditions-mobile.png", fullPage: true });

  const trendEnd = new Date();
  const trendStart = new Date(trendEnd.getTime() - 3 * 24 * 60 * 60 * 1000);
  const smokeTrend = {
    sensor_device_id: "smoke-sensor",
    range_start: trendStart.toISOString(),
    range_end: trendEnd.toISOString(),
    points: [
      { measured_at: trendStart.toISOString(), value: 34.0 },
      { measured_at: new Date(trendStart.getTime() + 36 * 60 * 60 * 1000).toISOString(), value: 48.5 },
      { measured_at: trendEnd.toISOString(), value: 41.0 },
    ],
    latest: 41.0,
    minimum: 34.0,
    maximum: 48.5,
    error: "",
  };
  const wizardResponse = await page.goto(new URL(setupHref, baseUrl).href, { waitUntil: "networkidle0" });
  assert.equal(wizardResponse.status(), 200);
  assert.equal(await page.$eval(".back-link", (link) => link.getAttribute("href")), `/fields/${fieldId}#monitoring`);
  assert.equal(await page.$eval('input[name="field_id"]', (input) => input.value), fieldId);
  assert.match(await page.$eval("#post-watering-sensor-trend", (section) => section.innerText || ""), /選択センサーの直近3日/);
  await page.click("#wizard-next");
  await page.waitForSelector('[data-wizard-step="1"].active #post-watering-sensor-trend');
  await page.waitForFunction(() => document.querySelector("#sensor-trend-status")?.textContent !== "直近3日分を読み込んでいます。");
  await page.evaluate((trend) => {
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      if (String(input).includes("/local/api/settings/post-watering-moisture/trend")) {
        return Promise.resolve(new Response(JSON.stringify(trend), { status: 200, headers: { "Content-Type": "application/json" } }));
      }
      return originalFetch(input, init);
    };
    const alternativeSensor = [...document.querySelectorAll('input[name="sensor_device_id"]')].find((input) => !input.checked);
    alternativeSensor?.click();
  }, smokeTrend);
  await page.waitForSelector("#sensor-trend-chart .moisture-line");
  assert.equal(await page.$eval("#sensor-trend-latest", (value) => value.textContent), "41.0%");
  const trendBounds = await page.$eval("#post-watering-sensor-trend", (section) => ({ scrollWidth: section.scrollWidth, clientWidth: section.clientWidth }));
  assert(trendBounds.scrollWidth <= trendBounds.clientWidth, `sensor trend must not overflow on mobile: ${trendBounds.scrollWidth}px > ${trendBounds.clientWidth}px`);
  await page.screenshot({ path: "/tmp/ina-post-watering-trend-mobile.png", fullPage: true });
  assert.deepEqual(browserErrors, []);

  process.stdout.write(JSON.stringify({
    cards: fieldCardCount,
    screenshots: [
      "/tmp/ina-field-notification-conditions-desktop.png",
      "/tmp/ina-field-notification-conditions-mobile.png",
      "/tmp/ina-post-watering-trend-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
