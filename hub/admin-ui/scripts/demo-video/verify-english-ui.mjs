import assert from "node:assert/strict";

import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const japaneseText = /[\u3040-\u30ff\u3400-\u9fff]/;
const browserErrors = [];
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

async function openEnglishPage(path, readySelector) {
  const url = new URL(path, baseUrl);
  url.searchParams.set("lang", "en");
  await page.goto(url.href, { waitUntil: "networkidle0" });
  await page.waitForSelector(readySelector, { visible: true });
  await page.waitForFunction(() => document.body?.dataset.uiLocaleReady === "true");
  await page.waitForFunction(() => !/[\u3040-\u30ff\u3400-\u9fff]/.test(document.body.innerText));
  assert.equal(await page.$eval("html", (element) => element.lang), "en");
  assert.equal(
    await page.$eval('[data-locale-option="en"]', (element) => element.getAttribute("aria-current")),
    "true",
  );
  const visibleText = await page.$eval("body", (element) => element.innerText);
  assert.doesNotMatch(visibleText, japaneseText, `Japanese text remains on ${url.pathname}${url.search}`);
  const untranslatedPlaceholders = await page.$$eval("[placeholder]", (elements) => elements
    .map((element) => ({ placeholder: element.getAttribute("placeholder") || "", visible: element.getClientRects().length > 0 }))
    .filter((item) => item.visible && /[\u3040-\u30ff\u3400-\u9fff]/.test(item.placeholder)));
  assert.deepEqual(untranslatedPlaceholders, [], `Japanese placeholder remains on ${url.pathname}${url.search}`);
}

try {
  await page.goto(new URL("/fields/demo-strawberry-field", baseUrl).href, { waitUntil: "networkidle0" });
  await page.waitForSelector('[data-locale-option="ja"][aria-current="true"]', { visible: true });
  assert.equal(await page.$eval("html", (element) => element.lang), "ja");
  assert.match(await page.$eval("body", (element) => element.innerText), japaneseText);
  assert.match(
    await page.$eval('[data-locale-option="en"]', (element) => element.getAttribute("href")),
    /(?:\?|&)lang=en/,
  );

  await openEnglishPage("/fields/demo-strawberry-field", "#field-status-dashboard");
  await openEnglishPage("/fields/demo-strawberry-field/calendar", ".calendar-workspace-tabs");

  const reviewCard = '[data-kanban-status="awaiting_review"] .calendar-kanban-card';
  await page.waitForSelector(reviewCard, { visible: true });
  await page.$eval(reviewCard, (element) => element.click());
  await page.waitForSelector(".calendar-action-detail-dialog [data-calendar-dialog-close]", { visible: true });
  await page.waitForFunction(() => {
    const dialog = document.querySelector(".calendar-action-detail-dialog");
    return dialog && !/[\u3040-\u30ff\u3400-\u9fff]/.test(dialog.innerText);
  });
  assert.doesNotMatch(
    await page.$eval(".calendar-action-detail-dialog", (element) => element.innerText),
    japaneseText,
  );
  assert.doesNotMatch(
    await page.$eval(".calendar-action-detail-dialog textarea", (element) => element.getAttribute("placeholder") || ""),
    japaneseText,
  );
  await page.$eval("[data-calendar-dialog-close]", (element) => element.click());

  await openEnglishPage("/mqtt-devices/INADS-DEMO-WTR-001?tab=overview", ".priority-panel");
  assert.equal(
    await page.$eval(".extension-tab-button", (element) => getComputedStyle(element, "::after").content),
    '"Add-on"',
  );

  await openEnglishPage("/mqtt-devices/INADS-DEMO-WTR-001?tab=settings", "#watering-schedules");
  const japaneseHref = await page.$eval('[data-locale-option="ja"]', (element) => element.getAttribute("href"));
  assert.match(japaneseHref, /tab=settings/);
  assert.doesNotMatch(japaneseHref, /(?:\?|&)lang=/);

  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));
  console.log(JSON.stringify({ japaneseDefault: true, englishPages: 4, managerReview: true, visibleJapanese: 0, browserErrors: 0 }, null, 2));
} finally {
  await browser.close();
}
