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
page.on("console", (message) => { if (message.type() === "error") browserErrors.push(message.text()); });

const routes = [
  ["個人設定", "/preferences"],
  ["圃場一覧", "/fields"],
  ["圃場詳細", "/fields/demo-strawberry-field"],
  ["年間栽培カレンダー", "/fields/demo-strawberry-field/calendar"],
  ["機器一覧", "/mqtt-devices"],
  ["機器詳細", "/mqtt-devices/INADS-DEMO-WTR-001"],
  ["アプリ設定", "/settings"],
];

async function auditRoute(label, route, viewport) {
  await page.setViewport({ ...viewport, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}${route}`, { waitUntil: "networkidle0" });
  await page.emulateMediaFeatures([{ name: "prefers-reduced-motion", value: "reduce" }]);
  await page.waitForFunction(() => document.body && document.body.innerText.trim().length > 0);

  const result = await page.evaluate(() => {
    const visible = (element) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.visibility !== "hidden" && style.display !== "none" && rect.width > 8 && rect.height > 8;
    };
    const namedBy = (element) => {
      const direct = element.getAttribute("aria-label") || element.getAttribute("title") || element.textContent?.trim();
      if (direct) return direct;
      const ids = (element.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean);
      const referenced = ids.map((id) => document.getElementById(id)?.textContent?.trim()).filter(Boolean).join(" ");
      if (referenced) return referenced;
      if (element.id) {
        const escaped = CSS.escape(element.id);
        const label = document.querySelector(`label[for="${escaped}"]`);
        if (label?.textContent?.trim()) return label.textContent.trim();
      }
      return element.closest("label")?.textContent?.trim() || "";
    };
    const unnamed = Array.from(document.querySelectorAll("button, a[href], input:not([type='hidden']), select, textarea, [role='button']"))
      .filter(visible)
      .filter((element) => !namedBy(element))
      .map((element) => `${element.tagName.toLowerCase()}#${element.id || "-"}.${element.className || "-"}`);
    const undersized = Array.from(document.querySelectorAll("button, input:not([type='checkbox']):not([type='radio']):not([type='range']):not([type='hidden']), select"))
      .filter(visible)
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { element, width: rect.width, height: rect.height };
      })
      .filter((item) => item.height < 47.5)
      .map((item) => `${item.element.tagName.toLowerCase()}#${item.element.id || "-"}:${item.height.toFixed(1)}px`);
    const missingAlt = Array.from(document.querySelectorAll("img"))
      .filter(visible)
      .filter((image) => !image.hasAttribute("alt"))
      .map((image) => image.getAttribute("src") || "unknown image");
    const ids = Array.from(document.querySelectorAll("[id]")).map((element) => element.id).filter(Boolean);
    const duplicateIds = [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
    return {
      title: document.title,
      h1Count: document.querySelectorAll("h1").length,
      unnamed,
      undersized,
      missingAlt,
      duplicateIds,
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      viewportMeta: document.querySelector('meta[name="viewport"]')?.getAttribute("content") || "",
      infiniteAnimations: document.getAnimations().filter((animation) => {
        const timing = animation.effect?.getComputedTiming();
        return animation.playState === "running" && timing?.iterations === Infinity;
      }).length,
    };
  });

  assert.match(result.viewportMeta, /width=device-width/, `${label} must use the device viewport`);
  assert.equal(result.h1Count, 1, `${label} must expose one page heading`);
  assert.deepEqual(result.unnamed, [], `${label} has unnamed controls`);
  assert.deepEqual(result.undersized, [], `${label} has controls below 48px`);
  assert.deepEqual(result.missingAlt, [], `${label} has images without alt text`);
  assert.deepEqual(result.duplicateIds, [], `${label} has duplicate element identifiers`);
  assert(result.overflow <= 1, `${label} overflows ${viewport.width}px viewport by ${result.overflow}px`);
  assert.equal(result.infiniteAnimations, 0, `${label} must stop repeating motion when reduced motion is requested`);

  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const active = document.activeElement;
    if (!active || active === document.body) return null;
    const rect = active.getBoundingClientRect();
    return { tag: active.tagName, width: rect.width, height: rect.height, visible: rect.bottom > 0 && rect.top < innerHeight };
  });
  assert(focus?.visible, `${label} must expose a visible keyboard focus target`);
  return result;
}

try {
  const audited = [];
  for (const [label, route] of routes) {
    audited.push({ label, mode: "desktop", result: await auditRoute(label, route, { width: 1280, height: 900 }) });
    audited.push({ label, mode: "mobile", result: await auditRoute(label, route, { width: 390, height: 844 }) });
  }
  await page.goto(`${baseUrl}/preferences`, { waitUntil: "networkidle0" });
  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.keyboard.press("Tab");
  await page.screenshot({ path: "/tmp/ina-accessibility-keyboard-mobile.png", fullPage: false });
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));
  process.stdout.write(JSON.stringify({ audited: audited.map(({ label, mode }) => `${label}:${mode}`), screenshot: "/tmp/ina-accessibility-keyboard-mobile.png" }, null, 2) + "\n");
} finally {
  await browser.close();
}
