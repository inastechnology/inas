import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39306";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outputDir = path.resolve(scriptDir, "../../src/ina_device_hub/static/inas-app");
await mkdir(outputDir, { recursive: true });

await prepareMarketingState();

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 960, deviceScaleFactor: 1 });

async function capture(name, url, readySelector, prepare) {
  await page.goto(`${baseUrl}${url}`, { waitUntil: "networkidle0" });
  await page.waitForSelector(readySelector, { visible: true });
  if (prepare) await prepare(page);
  await page.evaluate(() => window.scrollTo(0, 0));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert(overflow <= 1, `${name} has ${overflow}px horizontal overflow`);
  const outputPath = path.join(outputDir, name);
  await page.screenshot({ path: outputPath, fullPage: false });
  return outputPath;
}

try {
  const outputs = [];
  outputs.push(await capture(
    "hub-field-dashboard.png",
    "/fields/demo-strawberry-field",
    "#field-status-dashboard",
  ));
  outputs.push(await capture(
    "hub-cultivation-calendar.png",
    "/fields/demo-strawberry-field/calendar",
    ".calendar-workspace-tabs",
    async (targetPage) => {
      await targetPage.$$eval(".calendar-workspace-tabs button", (buttons) => {
        const button = buttons.find((item) => item.textContent?.includes("圃場の作業"));
        if (!(button instanceof HTMLButtonElement)) throw new Error("field work tab was not found");
        button.click();
      });
      await targetPage.waitForSelector(".calendar-kanban", { visible: true });
    },
  ));
  outputs.push(await capture(
    "hub-irrigation-device.png",
    "/mqtt-devices/INADS-DEMO-WTR-001?tab=overview",
    ".priority-panel",
  ));
  console.log(`Marketing Hub captures written:\n${outputs.join("\n")}`);
} finally {
  await browser.close();
}

async function prepareMarketingState() {
  const layout = await fetchJson(`${baseUrl}/local/api/fields/demo-strawberry-field/layout`);
  const root = layout.spaces.find((space) => space.id === layout.root_space_id);
  assert(root?.placements.length >= 3, "run `npm run smoke` once against the isolated demo server before capturing marketing images");

  const bundleUrl = `${baseUrl}/local/api/fields/demo-strawberry-field/plantings`;
  const bundle = await fetchJson(bundleUrl);
  const planting = bundle.plantings.find((item) => item.status === "active");
  assert(planting, "the marketing demo must contain an active crop");
  const calendar = bundle.calendars[planting.id];
  assert(calendar?.actions.length, "the marketing demo crop must contain calendar work");

  if (!calendar.actions.some((action) => action.status === "in_progress")) {
    const nextAction = calendar.actions.find((action) => action.status === "planned" && action.action_type === "fertilization")
      ?? calendar.actions.find((action) => action.status === "planned");
    assert(nextAction, "the marketing demo must contain work that can be started");
    await fetchJson(`${baseUrl}/local/api/plantings/${planting.id}/calendar/actions/${nextAction.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "in_progress", use_as_guidance: false }),
    });
  }
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || `request failed: ${response.status}`);
  return body;
}
