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

try {
  await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields/${fieldId}`, { waitUntil: "networkidle0" });
  assert.equal(await page.$$eval("[data-field-tab]", (tabs) => tabs.length), 5);
  assert.equal(await page.$eval("#field-installation-tree", (details) => details.hasAttribute("open")), false);
  assert.match(await page.$eval("#field-action-candidates", (panel) => panel.textContent || ""), /作業TODO/);
  assert.match(await page.$eval("#field-action-candidates", (panel) => panel.textContent || ""), /(そろそろ|今やる|期限超過)/);
  await page.screenshot({ path: "/tmp/ina-field-todo-desktop.png", fullPage: true });
  const calendarHref = await page.$eval(".calendar-task .task-open", (link) => link.href);
  const calendarPage = await browser.newPage();
  await calendarPage.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });
  await calendarPage.goto(calendarHref, { waitUntil: "networkidle0" });
  await calendarPage.waitForSelector(".calendar-drawer");
  await calendarPage.click(".care-profile-summary > summary");
  assert.match(await calendarPage.$eval(".care-profile-summary", (panel) => panel.textContent || ""), /EC/);
  assert.match(await calendarPage.$eval(".care-profile-summary", (panel) => panel.textContent || ""), /実施日起点/);
  await calendarPage.screenshot({ path: "/tmp/ina-care-profile-desktop.png", fullPage: true });
  await calendarPage.close();
  assert.match(await page.$eval("[data-field-tab='monitoring']", (tab) => tab.textContent || ""), /環境・設備/);
  await page.click("[data-field-tab='monitoring']");
  await page.waitForSelector("[data-tab-panel='monitoring']:not([hidden])");
  await page.screenshot({ path: "/tmp/ina-field-monitoring-desktop.png", fullPage: true });

  await page.click("[data-field-tab='cultivation']");
  await page.waitForSelector("[data-planting-form]");
  assert.match(await page.$eval("[data-tab-panel='cultivation']", (panel) => panel.textContent || ""), /年間カレンダーを開く/);
  assert.match(await page.$eval("[data-tab-panel='cultivation']", (panel) => panel.textContent || ""), /直近の履歴/);
  await page.screenshot({ path: "/tmp/ina-field-cultivation-desktop.png", fullPage: true });

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
    screenshots: [
      "/tmp/ina-field-todo-desktop.png",
      "/tmp/ina-care-profile-desktop.png",
      "/tmp/ina-field-monitoring-desktop.png",
      "/tmp/ina-field-cultivation-desktop.png",
      "/tmp/ina-field-cultivation-mobile.png",
      "/tmp/ina-ai-settings-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
