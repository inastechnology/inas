import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const fieldId = "demo-strawberry-field";
const apiUrl = `${baseUrl}/local/api/fields/${fieldId}/layout`;
const layout = await fetchJson(apiUrl);
const root = layout.spaces.find((space) => space.id === layout.root_space_id);
const greenhouse = root?.placements.find((placement) => placement.preset === "greenhouse");
const greenhouseSpace = layout.spaces.find((space) => space.id === greenhouse?.child_space_id);
const pot = root?.placements.find((placement) => placement.preset === "pot");
const sensorLocation = layout.spaces
  .flatMap((space) => space.placements.map((placement) => ({ space, placement })))
  .find(({ placement }) => placement.preset === "sensor");
assert(root && greenhouseSpace && pot && sensorLocation, "demo layout must contain a greenhouse, pot, and sensor");

const sensor = {
  ...sensorLocation.placement,
  x: Math.min(2, greenhouseSpace.grid.columns - sensorLocation.placement.width),
  y: Math.min(2, greenhouseSpace.grid.rows - sensorLocation.placement.height),
  binding: {
    ...sensorLocation.placement.binding,
    target_placement_ids: [pot.id],
  },
};
const nextLayout = {
  ...layout,
  spaces: layout.spaces.map((space) => ({
    ...space,
    placements: [
      ...space.placements.filter((placement) => placement.id !== sensor.id),
      ...(space.id === greenhouseSpace.id ? [sensor] : []),
    ],
  })),
};
await fetchJson(apiUrl, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(nextLayout) });

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
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/fields/${fieldId}/layout?space=${encodeURIComponent(greenhouseSpace.id)}`, { waitUntil: "networkidle0" });
  await page.waitForSelector('[data-layout-connection][data-external="true"]');
  const relation = await page.$$eval(
    '[data-layout-connection][data-external="true"]',
    (elements, sensorName) => elements.map((element) => element.textContent || "").find((value) => value.includes(`${sensorName}から`)) || "",
    sensor.name,
  );
  assert.match(relation, new RegExp(`${sensor.name}から${pot.name}へ計測`));
  assert.match(relation, /表示中の空間外へ接続/);
  assert.equal(await page.$$eval(".breadcrumbs button", (buttons) => buttons.length), 2);
  await page.screenshot({ path: "/tmp/ina-layout-cross-space-sensor.png", fullPage: true });
  assert.equal(browserErrors.length, 0, browserErrors.join("\n"));
  process.stdout.write(JSON.stringify({ relation, screenshot: "/tmp/ina-layout-cross-space-sensor.png" }, null, 2) + "\n");
} finally {
  await browser.close();
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `${response.status} ${response.statusText}`);
  return body;
}
