import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const cameraId = "INADS-DEMO-CAM-001";
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
  await page.setViewport({ width: 2000, height: 1120, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields/demo-strawberry-field`, { waitUntil: "networkidle0" });
  assert(await page.$(".field-camera-section"), "field overview must expose the current camera area");
  assert.equal(await page.$$(".field-camera-card").then((items) => items.length), 1);
  assert.equal(
    await page.$eval(".field-camera-media", (link) => link.getAttribute("href")),
    `/camera/${cameraId}`,
  );
  assert.equal(
    await page.$$eval(`a[href^="/mqtt-devices/${cameraId}"]`, (links) => links.length),
    0,
    "camera links must not open the generic MQTT detail",
  );
  await page.screenshot({ path: "/tmp/ina-field-camera-wide.png", fullPage: true });

  await page.goto(`${baseUrl}/camera/${cameraId}`, { waitUntil: "networkidle0" });
  assert.match(await page.$eval("h1", (heading) => heading.textContent || ""), /ハウス定点カメラ/);
  assert(await page.$("#live"), "camera detail must contain a live section");
  assert(await page.$("#captures"), "camera detail must contain capture history");
  assert(await page.$("#settings"), "camera detail must contain connection settings");
  assert.match(await page.$eval("#settings", (section) => section.textContent || ""), /確認済みの方式はRTSP/);
  assert.equal(await page.$$("#capture-gallery .capture-card").then((items) => items.length), 5);
  await page.click("#capture-gallery .capture-card");
  assert.equal(await page.$eval("#capture-dialog", (dialog) => dialog.open), true);
  await page.click("#close-lightbox");
  assert.equal(await page.$eval("#capture-dialog", (dialog) => dialog.open), false);
  assert(
    (await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1,
    "camera detail must not overflow at 2000px",
  );
  await page.screenshot({ path: "/tmp/ina-camera-detail-wide.png", fullPage: true });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await new Promise((resolve) => setTimeout(resolve, 250));
  assert(
    (await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)) <= 1,
    "camera detail must not overflow on mobile",
  );
  assert.equal(
    await page.$eval(".gallery-grid", (grid) => getComputedStyle(grid).gridTemplateColumns.split(" ").length),
    1,
  );
  await page.screenshot({ path: "/tmp/ina-camera-detail-mobile.png", fullPage: true });
  assert.deepEqual(browserErrors, []);
  console.log("camera detail smoke: ok");
} finally {
  await browser.close();
}
