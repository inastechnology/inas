import assert from "node:assert/strict";

import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const locales = ["ja", "en"];
const browserErrors = [];
const reports = [];
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

function localizedUrl(path, locale) {
  const url = new URL(path, baseUrl);
  if (locale === "en") url.searchParams.set("lang", "en");
  return url.href;
}

async function openPage(path, readySelector, locale) {
  const response = await page.goto(localizedUrl(path, locale), { waitUntil: "networkidle0" });
  assert.equal(response.status(), 200, `${path} returned ${response.status()}`);
  await page.waitForSelector(readySelector, { visible: true });
  await page.waitForFunction((expectedLocale) => (
    document.documentElement.lang === expectedLocale
    && document.body?.dataset.uiLocaleReady === "true"
  ), {}, locale);
}

async function assertContained(pageName, selectors) {
  const result = await page.evaluate((containerSelectors) => {
    const describe = (element) => {
      const className = typeof element.className === "string"
        ? element.className.trim().split(/\s+/).filter(Boolean).slice(0, 3).join(".")
        : "";
      return `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${className ? `.${className}` : ""}`;
    };
    const visible = (element) => {
      if (element.getClientRects().length === 0) return false;
      const style = getComputedStyle(element);
      return style.visibility !== "hidden" && style.display !== "none";
    };
    const escaped = [];
    let containers = 0;
    for (const selector of containerSelectors) {
      for (const container of document.querySelectorAll(selector)) {
        if (!visible(container)) continue;
        containers += 1;
        const bounds = container.getBoundingClientRect();
        for (const element of container.querySelectorAll("h1,h2,h3,h4,p,span,strong,small,a,button,input,textarea,select,img,svg")) {
          if (!visible(element) || element.closest(".context-help-panel")) continue;
          const style = getComputedStyle(element);
          if (style.position === "fixed") continue;
          const rect = element.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          if (rect.left < bounds.left - 1 || rect.right > bounds.right + 1) {
            escaped.push({
              container: describe(container),
              element: describe(element),
              left: Math.round(rect.left - bounds.left),
              right: Math.round(rect.right - bounds.right),
              text: element.textContent?.trim().replace(/\s+/g, " ").slice(0, 90) || "",
            });
          }
        }
      }
    }

    const controlOverlaps = [];
    for (const header of document.querySelectorAll(".calendar-kanban-column > header")) {
      if (!visible(header)) continue;
      const help = header.querySelector(":scope > .context-help > summary");
      if (!help || !visible(help)) continue;
      const helpRect = help.getBoundingClientRect();
      for (const element of header.querySelectorAll(":scope > div h3, :scope > div strong, :scope > small")) {
        if (!visible(element)) continue;
        const rect = element.getBoundingClientRect();
        const overlapWidth = Math.max(0, Math.min(helpRect.right, rect.right) - Math.max(helpRect.left, rect.left));
        const overlapHeight = Math.max(0, Math.min(helpRect.bottom, rect.bottom) - Math.max(helpRect.top, rect.top));
        if (overlapWidth > 1 && overlapHeight > 1) {
          controlOverlaps.push({ container: describe(header), first: describe(help), second: describe(element), overlap: [Math.round(overlapWidth), Math.round(overlapHeight)] });
        }
      }
    }

    for (const dateField of document.querySelectorAll(".calendar-action-date")) {
      if (!visible(dateField)) continue;
      const caption = dateField.querySelector(":scope > span");
      const input = dateField.querySelector(":scope > input");
      if (!caption || !input || !visible(caption) || !visible(input)) continue;
      const captionRect = caption.getBoundingClientRect();
      const inputRect = input.getBoundingClientRect();
      const overlapWidth = Math.max(0, Math.min(captionRect.right, inputRect.right) - Math.max(captionRect.left, inputRect.left));
      const overlapHeight = Math.max(0, Math.min(captionRect.bottom, inputRect.bottom) - Math.max(captionRect.top, inputRect.top));
      if (overlapWidth > 1 && overlapHeight > 1) {
        controlOverlaps.push({ container: describe(dateField), first: describe(caption), second: describe(input), overlap: [Math.round(overlapWidth), Math.round(overlapHeight)] });
      }
    }

    const clippedLabels = [];
    for (const container of document.querySelectorAll(".member-task-counts")) {
      if (!visible(container)) continue;
      const labels = [...container.querySelectorAll(".member-task-count")].filter(visible);
      for (let index = 0; index < labels.length; index += 1) {
        const label = labels[index];
        if (label.scrollWidth > label.clientWidth + 1) {
          clippedLabels.push({ element: describe(label), clientWidth: label.clientWidth, scrollWidth: label.scrollWidth, text: label.textContent?.trim() || "" });
        }
        const firstRect = label.getBoundingClientRect();
        for (const sibling of labels.slice(index + 1)) {
          const secondRect = sibling.getBoundingClientRect();
          const overlapWidth = Math.max(0, Math.min(firstRect.right, secondRect.right) - Math.max(firstRect.left, secondRect.left));
          const overlapHeight = Math.max(0, Math.min(firstRect.bottom, secondRect.bottom) - Math.max(firstRect.top, secondRect.top));
          if (overlapWidth > 1 && overlapHeight > 1) {
            controlOverlaps.push({ container: describe(container), first: describe(label), second: describe(sibling), overlap: [Math.round(overlapWidth), Math.round(overlapHeight)] });
          }
        }
      }
    }

    return {
      containers,
      escaped,
      controlOverlaps,
      clippedLabels,
      viewport: {
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      },
    };
  }, selectors);

  assert(result.containers > 0, `${pageName} did not expose any audited cards`);
  assert(result.viewport.scrollWidth <= result.viewport.clientWidth + 1, `${pageName} has page-level horizontal overflow: ${JSON.stringify(result.viewport)}`);
  assert.deepEqual(result.escaped, [], `${pageName} has content outside a card:\n${JSON.stringify(result.escaped, null, 2)}`);
  assert.deepEqual(result.controlOverlaps, [], `${pageName} has overlapping controls:\n${JSON.stringify(result.controlOverlaps, null, 2)}`);
  assert.deepEqual(result.clippedLabels, [], `${pageName} has clipped count labels:\n${JSON.stringify(result.clippedLabels, null, 2)}`);
  reports.push({ page: pageName, cards: result.containers });
}

try {
  for (const locale of locales) {
    await openPage("/fields/demo-strawberry-field", "#field-status-dashboard", locale);
    await assertContained(`${locale}:field`, [".range-card", ".candidate"]);

    await openPage("/fields/demo-strawberry-field/calendar", ".calendar-kanban", locale);
    await assertContained(`${locale}:work-board`, [
      ".calendar-kanban-column > header",
      ".calendar-kanban-card",
      ".member-task-summary-list button",
    ]);

    const reviewCard = '[data-kanban-status="awaiting_review"] .calendar-kanban-card';
    await page.waitForSelector(reviewCard, { visible: true });
    await page.$eval(reviewCard, (element) => element.click());
    await page.waitForSelector(".calendar-action-detail-dialog .manager-review-panel", { visible: true });
    await assertContained(`${locale}:manager-review`, [".manager-review-panel"]);

    await openPage("/mqtt-devices/INADS-DEMO-WTR-001?tab=overview", ".priority-panel", locale);
    await assertContained(`${locale}:device-overview`, [".priority-panel .metric", "#tab-overview .compact-grid > *"]);

    await openPage("/mqtt-devices/INADS-DEMO-WTR-001?tab=settings", "#watering-schedules", locale);
    await assertContained(`${locale}:irrigation-schedule`, ["#watering-schedules"]);
  }

  assert.deepEqual(browserErrors, [], `browser errors:\n${browserErrors.join("\n")}`);
  console.log(JSON.stringify({ viewport: "1600x900", locales, pages: reports.length, cards: reports.reduce((sum, item) => sum + item.cards, 0), overflow: 0, overlaps: 0 }, null, 2));
} finally {
  await browser.close();
}
