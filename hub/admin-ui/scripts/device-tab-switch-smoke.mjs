import assert from "node:assert/strict";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39303";
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const results = [];

async function assertChartsFit(page) {
  await page.waitForFunction(() => {
    const bodies = [...document.querySelectorAll(".chart-body")];
    return bodies.length > 0 && bodies.every((body) => {
      const graph = body.querySelector(".js-plotly-plot");
      return graph?._fullLayout && Math.abs(graph._fullLayout.width - body.clientWidth) <= 1;
    });
  });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
  assert(overflow <= 1, `monitoring must fit the viewport: ${overflow}px overflow`);
}

async function assertSelected(page, key) {
  assert.equal(await page.$eval(`.tab-button[data-tab-key="${key}"]`, (button) => button.getAttribute("aria-selected")), "true");
  assert.equal(await page.$$eval('.tab-panel:not([hidden])', (panels) => panels.length), 1);
}

try {
  for (const [kind, width] of [["WTR", 1440], ["ENV", 390], ["FGT", 390]]) {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (error) => errors.push(error.message));
    await page.setViewport({ width, height: 960 });
    let chartRequests = 0;
    let plotlyRequests = 0;
    let releaseCharts;
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname;
      if (path.endsWith("/charts")) {
        chartRequests += 1;
        releaseCharts = () => request.continue();
      } else {
        if (path.endsWith("/plotly.min.js")) plotlyRequests += 1;
        request.continue();
      }
    });
    await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-${kind}-001`, { waitUntil: "networkidle0" });
    assert.equal(chartRequests, 0, "overview must not fetch history");
    assert.equal(plotlyRequests, 0, "overview must not load Plotly");

    const chartsRequested = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith("/charts"));
    await page.click('.tab-button[data-tab-key="monitoring"]');
    await assertSelected(page, "monitoring");
    await chartsRequested;
    assert.equal(await page.$eval("#tab-monitoring", (panel) => panel.hidden), false, "tab must open before the history response arrives");
    await page.click('.tab-button[data-tab-key="overview"]');
    await assertSelected(page, "overview");
    const response = page.waitForResponse((response) => new URL(response.url()).pathname.endsWith("/charts"));
    await releaseCharts();
    await response;
    await page.waitForNetworkIdle();
    assert.equal(await page.$$(".chart-body .js-plotly-plot").then((graphs) => graphs.length), 0, "history arriving after leaving the tab must not render while hidden");

    await page.click('.tab-button[data-tab-key="monitoring"]');
    await assertChartsFit(page);
    const graphIds = await page.$$eval(".js-plotly-plot", (graphs) => graphs.map((graph) => graph.id));
    assert(graphIds.length >= 2, "the device must have multiple graphs");
    await page.click('.chart-card [data-range-days="14"]');
    const selectedRange = await page.$eval(".js-plotly-plot", (graph) => graph.layout.xaxis.range);
    const screenshot = `/tmp/ina-device-tabs-${kind.toLowerCase()}-${width}.png`;
    await page.screenshot({ path: screenshot, fullPage: true });

    await page.click('.tab-button[data-tab-key="settings"]');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    // The sticky tab remains clickable far down the settings panel.
    await page.click('.tab-button[data-tab-key="monitoring"]');
    await assertSelected(page, "monitoring");
    const panelTop = await page.$eval("#tab-monitoring", (panel) => panel.getBoundingClientRect().top);
    assert(panelTop >= 0 && panelTop < 180, `switching from long settings must show the start of monitoring: ${panelTop}`);
    assert.deepEqual(await page.$eval(".js-plotly-plot", (graph) => graph.layout.xaxis.range), selectedRange, "revisiting must preserve the selected range");

    await page.click('.tab-button[data-tab-key="overview"]');
    await page.setViewport({ width: width === 390 ? 1440 : 390, height: 960 });
    await page.focus('.tab-button[data-tab-key="overview"]');
    await page.keyboard.press("ArrowRight");
    await assertSelected(page, "monitoring");
    await assertChartsFit(page);
    assert.deepEqual(await page.$$eval(".js-plotly-plot", (graphs) => graphs.map((graph) => graph.id)), graphIds);
    assert.equal(chartRequests, 1, "revisiting must reuse the same history response");
    assert.equal(plotlyRequests, 1);
    assert.deepEqual(errors, []);
    results.push({ kind, width, charts: graphIds.length, screenshot });
    await page.close();
  }
  for (const failedPath of ["/charts", "/plotly.min.js"]) {
    const page = await browser.newPage();
    let failures = 0;
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (!failures && new URL(request.url()).pathname.endsWith(failedPath)) {
        failures += 1;
        request.respond({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "temporary test failure" }) });
      } else request.continue();
    });
    await page.goto(`${baseUrl}/mqtt-devices/INADS-DEMO-WTR-001?tab=monitoring`, { waitUntil: "networkidle0" });
    await page.waitForFunction(() => document.querySelector(".chart-body .empty")?.textContent.includes("再試行"));
    await assertSelected(page, "monitoring");
    await page.click('.tab-button[data-tab-key="monitoring"]');
    await assertChartsFit(page);
    assert.equal(failures, 1);
    results.push({ retry: failedPath });
    await page.close();
  }
  process.stdout.write(`${JSON.stringify(results, null, 2)}\n`);
} finally {
  await browser.close();
}
