import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39306";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(scriptDir, "../../doc/jp/assets");
await mkdir(outputDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });

try {
  await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const response = await page.goto(`${baseUrl}/inas-app`, { waitUntil: "networkidle0" });
  assert.equal(response?.status(), 200);
  assert.match(await page.$eval("h1", (heading) => heading.textContent || ""), /育てる判断を/);
  assert.equal(await page.$$(".product-tour .browser-frame").then((items) => items.length), 3);
  assert.equal(await page.$$(".source-path").then((items) => items.length), 2);
  assert.match(await page.$eval("#opensource", (section) => section.innerText), /自分でつくる/);
  assert.match(await page.$eval("#opensource", (section) => section.innerText), /提供準備中/);
  await assertNoHorizontalOverflow(page, "desktop");
  const desktopPath = path.join(outputDir, "inas-app-lp-desktop.png");
  await page.screenshot({ path: desktopPath, fullPage: true });

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.reload({ waitUntil: "networkidle0" });
  await assertNoHorizontalOverflow(page, "mobile");
  const mobilePath = path.join(outputDir, "inas-app-lp-mobile.png");
  await page.screenshot({ path: mobilePath, fullPage: true });

  await page.emulateMediaType("print");
  await page.setViewport({ width: 794, height: 1123, deviceScaleFactor: 1 });
  await page.reload({ waitUntil: "networkidle0" });
  assert.equal(await page.$eval(".site-header", (header) => getComputedStyle(header).display), "none");
  const printSheetHeights = await page.$$eval(".print-sheet", (sheets) => sheets.map((sheet) => ({
    className: sheet.className,
    height: Math.round(sheet.getBoundingClientRect().height),
  })));
  for (const sheet of printSheetHeights) {
    assert(sheet.height <= 1055, `${sheet.className} exceeds one A4 content page: ${sheet.height}px`);
  }
  const printPreviewPath = path.join(outputDir, "inas-app-brochure-preview.png");
  await page.screenshot({ path: printPreviewPath, fullPage: true });
  const pdfPath = path.join(outputDir, "inas-app-brochure.pdf");
  await page.pdf({
    path: pdfPath,
    format: "A4",
    printBackground: true,
    preferCSSPageSize: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });

  assert.equal(errors.length, 0, errors.join("\n"));
  console.log(`INAS App marketing page verified (${printSheetHeights.map((sheet) => `${sheet.className}: ${sheet.height}px`).join(", ")}):\n${desktopPath}\n${mobilePath}\n${printPreviewPath}\n${pdfPath}`);
} finally {
  await browser.close();
}

async function assertNoHorizontalOverflow(targetPage, label) {
  const dimensions = await targetPage.evaluate(() => ({
    viewport: window.innerWidth,
    document: document.documentElement.scrollWidth,
  }));
  assert(dimensions.document - dimensions.viewport <= 1, `${label} has ${dimensions.document - dimensions.viewport}px horizontal overflow`);
}
