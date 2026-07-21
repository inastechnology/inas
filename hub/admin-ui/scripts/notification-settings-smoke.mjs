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
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

try {
  await page.setViewport({ width: 1280, height: 900, deviceScaleFactor: 1 });
  const response = await page.goto(`${baseUrl}/settings?section=notifications`, { waitUntil: "networkidle0" });
  assert.equal(response.status(), 200);
  assert.equal(await page.$eval('[data-settings-nav="notifications"]', (item) => item.classList.contains("active")), true);
  assert.equal(await page.$eval("#notifications h2", (heading) => heading.textContent?.trim()), "通知");
  assert.match(await page.$eval("#notifications", (section) => section.innerText || ""), /今日の栽培作業/);
  assert.doesNotMatch(await page.$eval("#notifications", (section) => section.innerText || ""), /毎朝4:00/, "long notification help must start collapsed");
  await page.click('summary[aria-label="栽培作業通知の説明を開く"]');
  assert.match(await page.$eval("#notifications", (section) => section.innerText || ""), /毎朝4:00/);
  await page.keyboard.press("Escape");
  assert.match(await page.$eval("#notifications", (section) => section.innerText || ""), /hub-demo\.inas-technologies\.com/);
  assert.doesNotMatch(await page.$eval("#notifications", (section) => section.innerText || ""), /127\.0\.0\.1|localhost/);
  assert.equal(await page.$eval('input[name="plant_task_reminder_days_before"]', (input) => input.value), "7");
  assert.equal(await page.$eval('input[name="notify_mqtt_activity"]', (input) => input.checked), false);
  assert.equal(await page.$$eval('#notification-settings-form input[role="switch"]', (inputs) => inputs.length), 10);
  assert.equal(await page.$$eval("#notification-settings-form .notification-switch-control", (controls) => controls.length), 10);
  assert.equal(
    await page.$eval('input[name="enabled"] + .notification-switch-control', (control) => getComputedStyle(control, "::before").content),
    '"ON"',
  );
  assert.equal(
    await page.$eval('input[name="notify_mqtt_activity"] + .notification-switch-control', (control) => getComputedStyle(control, "::before").content),
    '"OFF"',
  );
  assert.equal(
    await page.$$eval(
      "#notification-settings-form .notification-switch",
      (labels) => labels.filter((label) => label.getClientRects().length > 0).every((label) => label.getBoundingClientRect().height >= 48),
    ),
    true,
  );
  assert.equal(await page.$eval("#notification-settings-form [data-stateful-submit]", (button) => button.disabled), true);

  await page.click("#open-disable-all-notifications");
  assert.equal(await page.$eval("#disable-all-notifications-dialog", (dialog) => dialog.open), true);
  await page.screenshot({ path: "/tmp/ina-notification-settings-confirm-desktop.png", fullPage: true });
  await page.click("[data-close-disable-all]");
  assert.equal(await page.$eval("#disable-all-notifications-dialog", (dialog) => dialog.open), false);

  await page.click('input[name="plant_task_notify_during_window"]');
  assert.equal(await page.$eval("#notification-settings-form [data-stateful-submit]", (button) => button.disabled), false);
  await page.screenshot({ path: "/tmp/ina-notification-settings-desktop.png", fullPage: true });
  await (await page.$("#notifications")).screenshot({ path: "/tmp/ina-notification-settings-section-desktop.png" });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/settings?section=notifications`, { waitUntil: "networkidle0" });
  const bounds = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(bounds.scrollWidth <= bounds.clientWidth, "notification settings must not overflow on mobile");
  assert.equal(await page.$$eval(".settings-nav a", (items) => items.length), 4);
  await page.screenshot({ path: "/tmp/ina-notification-settings-mobile.png", fullPage: true });
  await (await page.$("#notifications")).screenshot({ path: "/tmp/ina-notification-settings-section-mobile.png" });
  assert.deepEqual(browserErrors, []);

  process.stdout.write(JSON.stringify({
    screenshots: [
      "/tmp/ina-notification-settings-confirm-desktop.png",
      "/tmp/ina-notification-settings-desktop.png",
      "/tmp/ina-notification-settings-section-desktop.png",
      "/tmp/ina-notification-settings-mobile.png",
      "/tmp/ina-notification-settings-section-mobile.png",
    ],
  }, null, 2) + "\n");
} finally {
  await browser.close();
}
