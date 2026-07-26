import assert from "node:assert/strict";
import { createServer } from "node:http";
import { createRequire } from "node:module";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const lpRoot = path.resolve(scriptDir, "..");
const requireFromAdminUi = createRequire(path.resolve(scriptDir, "../../hub/admin-ui/package.json"));
const puppeteer = requireFromAdminUi("puppeteer-core");
let baseUrl = process.env.LP_AUDIT_URL || "";
const widths = [320, 360, 375, 390, 430, 768, 820, 1024, 1280, 1440, 1600, 1920, 2000, 2560];
const screenshotDir = process.env.LP_AUDIT_SCREENSHOT_DIR || "";
const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".webp", "image/webp"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".mp4", "video/mp4"],
  [".vtt", "text/vtt; charset=utf-8"],
]);
const cardSelector = [
  ".field-status-card",
  ".problem-grid article",
  ".outcome-list li",
  ".video-poster",
  ".screen-frame",
  ".audience-panels article:not([hidden])",
  ".open-intro",
  ".open-source article",
  ".interest",
  ".interest-form",
  ".mobile-conversion-bar:not(.hidden)",
  ".video-dialog[open]",
].join(",");

let server;
if (!baseUrl) {
  server = createServer(async (request, response) => {
    const requestUrl = new URL(request.url, "http://127.0.0.1");
    const relativePath = requestUrl.pathname === "/" ? "index.html" : decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
    const resolvedPath = path.resolve(lpRoot, relativePath);
    if (!resolvedPath.startsWith(`${lpRoot}${path.sep}`) && resolvedPath !== path.join(lpRoot, "index.html")) {
      response.writeHead(403).end("Forbidden");
      return;
    }
    try {
      const content = await readFile(resolvedPath);
      response.writeHead(200, {
        "Content-Type": mimeTypes.get(path.extname(resolvedPath)) || "application/octet-stream",
        "Cache-Control": "no-store",
      });
      response.end(content);
    } catch {
      response.writeHead(404).end("Not found");
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  baseUrl = `http://127.0.0.1:${address.port}/`;
}

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
});
const page = await browser.newPage();
const results = [];

async function inspect(width, state) {
  const audit = await page.evaluate((selector) => {
    const label = (element) => {
      const className = typeof element.className === "string" ? element.className.trim().split(/\s+/).slice(0, 3).join(".") : "";
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className ? `.${className}` : ""}`;
    };
    const root = document.documentElement;
    const hero = document.querySelector(".hero");
    const heroLead = document.querySelector(".hero-lead");
    const heroTitle = document.querySelector(".hero h1");
    const heroTitleRect = heroTitle?.getBoundingClientRect();
    const heroTitleOverflow = heroTitleRect
      ? [...heroTitle.querySelectorAll(".hero-title-line")]
        .map((element) => ({ text: element.textContent?.trim() || "", rect: element.getBoundingClientRect() }))
        .filter(({ rect }) => rect.left < heroTitleRect.left - 1 || rect.right > heroTitleRect.right + 1)
        .map(({ text, rect }) => ({
          text,
          left: Math.round(rect.left - heroTitleRect.left),
          right: Math.round(rect.right - heroTitleRect.right),
        }))
      : [{ text: "hero title not found", left: 0, right: 0 }];
    const cards = [...document.querySelectorAll(selector)].filter((element) => element.getClientRects().length > 0);
    const cardOverflow = [];
    for (const card of cards) {
      const rect = card.getBoundingClientRect();
      const cardStyle = getComputedStyle(card);
      const scrollOverflow = (
        (cardStyle.overflowX === "visible" && card.scrollWidth > card.clientWidth + 1)
      );
      const escapedChildren = [...card.querySelectorAll("*")]
        .filter((element) => (
          element.getClientRects().length > 0
          && getComputedStyle(element).position !== "fixed"
          && !element.closest(".form-trap")
        ))
        .map((element) => ({ element, rect: element.getBoundingClientRect() }))
        .filter(({ rect: childRect }) => (
          childRect.left < rect.left - 1
          || childRect.right > rect.right + 1
        ))
        .map(({ element, rect: childRect }) => ({
          element: label(element),
          left: Math.round(childRect.left - rect.left),
          right: Math.round(childRect.right - rect.right),
          top: Math.round(childRect.top - rect.top),
          bottom: Math.round(childRect.bottom - rect.bottom),
          text: element.textContent?.trim().replace(/\s+/g, " ").slice(0, 80) || "",
        }));
      const textOverflow = [...card.querySelectorAll("h1,h2,h3,p,li,a,button,span,strong,small,label,legend")]
        .filter((element) => element.getClientRects().length > 0 && !element.closest(".form-trap"))
        .filter((element) => element.scrollWidth > element.clientWidth + 1)
        .map((element) => ({
          element: label(element),
          client: [element.clientWidth, element.clientHeight],
          scroll: [element.scrollWidth, element.scrollHeight],
          text: element.textContent?.trim().replace(/\s+/g, " ").slice(0, 100) || "",
        }));
      if (scrollOverflow || escapedChildren.length || textOverflow.length) {
        cardOverflow.push({
          card: label(card),
          client: [card.clientWidth, card.clientHeight],
          scroll: [card.scrollWidth, card.scrollHeight],
          escapedChildren: escapedChildren.slice(0, 8),
          textOverflow: textOverflow.slice(0, 8),
        });
      }
    }
    return {
      page: { clientWidth: root.clientWidth, scrollWidth: root.scrollWidth },
      hero: {
        height: Math.round(hero?.getBoundingClientRect().height || 0),
        leadWidth: Math.round(heroLead?.getBoundingClientRect().width || 0),
      },
      heroTitleOverflow,
      cardOverflow,
      visibleFixedOverlays: [...document.querySelectorAll(".mobile-conversion-bar")]
        .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).position === "fixed")
        .map((element) => label(element)),
    };
  }, cardSelector);
  results.push({ width, state, ...audit });
}

try {
  if (screenshotDir) await mkdir(screenshotDir, { recursive: true });
  for (const width of widths) {
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    const response = await page.goto(baseUrl, { waitUntil: "networkidle0" });
    assert.equal(response.status(), 200, `${baseUrl} returned ${response.status()}`);
    await inspect(width, "page");
    if (screenshotDir && [320, 390, 1440].includes(width)) {
      const cards = await page.$$(cardSelector);
      for (let index = 0; index < cards.length; index += 1) {
        const bounds = await cards[index].boundingBox();
        if (!bounds || bounds.width < 1 || bounds.height < 1) continue;
        await cards[index].screenshot({ path: path.join(screenshotDir, `${width}-card-${String(index + 1).padStart(2, "0")}.png`) });
      }
    }

    if ([320, 375, 390, 768, 1440].includes(width)) {
      await page.click("[data-open-video]");
      await page.waitForSelector("[data-video-dialog][open]", { visible: true });
      await inspect(width, "video-dialog-ja");
      if (screenshotDir && [320, 390, 1440].includes(width)) {
        await page.$eval("[data-video-dialog]", (dialog) => dialog.scrollTop = 0);
        const dialog = await page.$("[data-video-dialog]");
        assert(dialog);
        await dialog.screenshot({ path: path.join(screenshotDir, `${width}-video-ja.png`) });
      }
      await page.click('[data-video-locale="en"]');
      await inspect(width, "video-dialog-en");
      if (screenshotDir && [320, 390, 1440].includes(width)) {
        const dialog = await page.$("[data-video-dialog]");
        assert(dialog);
        await dialog.screenshot({ path: path.join(screenshotDir, `${width}-video-en.png`) });
      }
      await page.click("[data-close-video]");
    }
  }

  const failures = results.filter((result) => (
    result.page.scrollWidth > result.page.clientWidth + 1
    || (result.width >= 1280 && (result.hero.height > 900 || result.hero.leadWidth < 400))
    || result.heroTitleOverflow.length > 0
    || result.cardOverflow.length > 0
    || result.visibleFixedOverlays.length > 0
  ));
  assert.deepEqual(failures, [], `responsive overflow detected:\n${JSON.stringify(failures, null, 2)}`);
  console.log(JSON.stringify({ baseUrl, widths, states: results.length, overflow: 0 }, null, 2));
} finally {
  await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
}
