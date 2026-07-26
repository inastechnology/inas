import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const artifactDir = join(root, "artifacts");
const requireFromDocsSite = createRequire(new URL("../../docs-site/package.json", import.meta.url));
const puppeteer = requireFromDocsSite("puppeteer-core");
const deckUrl = process.env.DECK_URL || "http://127.0.0.1:4330/pitch-deck/";

await mkdir(artifactDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

const errors = [];
const overflows = [];

try {
  const page = await browser.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const response = await page.goto(deckUrl, { waitUntil: "networkidle0" });
  assert.equal(response?.status(), 200, "pitch deck must return HTTP 200");

  const slides = await page.$$(".slide");
  assert.equal(slides.length, 13, "pitch deck must contain 13 slides");
  assert.equal(await page.$eval("[data-total]", (element) => element.textContent), "13");
  assert.equal(
    await page.$eval("#slide-1 h1", (element) => element.textContent.replace(/\s+/g, " ").trim()),
    "農を、次の世代へ渡せる形に。",
  );
  assert.equal(
    await page.$eval("#slide-13 h2", (element) => element.textContent.replace(/\s+/g, " ").trim()),
    "自然との関係を失わずに、食糧をつくり続ける。",
  );
  await page.$eval(".deck-controls", (element) => { element.style.display = "none"; });

  const results = [];
  for (let index = 0; index < slides.length; index += 1) {
    const slide = slides[index];
    const dimensions = await slide.evaluate((element) => ({
      clientWidth: element.clientWidth,
      clientHeight: element.clientHeight,
      scrollWidth: element.scrollWidth,
      scrollHeight: element.scrollHeight,
      title: element.dataset.title,
    }));
    if (dimensions.scrollWidth > dimensions.clientWidth + 1) {
      overflows.push(`slide ${index + 1} overflows horizontally: ${JSON.stringify(dimensions)}`);
    }
    if (dimensions.scrollHeight > dimensions.clientHeight + 1) {
      overflows.push(`slide ${index + 1} overflows vertically: ${JSON.stringify(dimensions)}`);
    }
    const screenshot = join(artifactDir, `slide-${String(index + 1).padStart(2, "0")}.png`);
    await slide.screenshot({ path: screenshot });
    results.push({ slide: index + 1, screenshot, ...dimensions });
  }

  await page.keyboard.press("Home");
  await page.keyboard.press("ArrowRight");
  await page.waitForFunction(() => document.querySelector("[data-current]")?.textContent === "2");
  assert.equal(await page.$eval("[data-current]", (element) => element.textContent), "2");
  assert.deepEqual(errors, [], `browser errors: ${errors.join(" | ")}`);
  assert.deepEqual(overflows, [], `slide overflows: ${overflows.join(" | ")}`);

  console.log(JSON.stringify({ deckUrl, results }, null, 2));
} finally {
  await browser.close();
}
