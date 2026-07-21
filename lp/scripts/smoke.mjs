import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { createServer } from "node:http";
import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const lpRoot = path.resolve(scriptDir, "..");
const requireFromAdminUi = createRequire(path.resolve(lpRoot, "../hub/admin-ui/package.json"));
const puppeteer = requireFromAdminUi("puppeteer-core");
const mimeTypes = new Map([
  [".html", "text/html; charset=utf-8"],
  [".css", "text/css; charset=utf-8"],
  [".js", "text/javascript; charset=utf-8"],
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".mp4", "video/mp4"],
]);
const receivedLeads = [];

const server = createServer(async (request, response) => {
  const requestUrl = new URL(request.url, "http://127.0.0.1");
  if (request.method === "POST" && requestUrl.pathname === "/api/leads") {
    let body = "";
    request.setEncoding("utf8");
    for await (const chunk of request) body += chunk;
    receivedLeads.push(JSON.parse(body));
    response.writeHead(201, { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" });
    response.end(JSON.stringify({ ok: true }));
    return;
  }
  const relativePath = requestUrl.pathname === "/" ? "index.html" : decodeURIComponent(requestUrl.pathname).replace(/^\/+/, "");
  const resolvedPath = path.resolve(lpRoot, relativePath);
  if (!resolvedPath.startsWith(`${lpRoot}${path.sep}`) && resolvedPath !== path.join(lpRoot, "index.html")) {
    response.writeHead(403).end("Forbidden");
    return;
  }
  try {
    const content = await readFile(resolvedPath);
    response.writeHead(200, { "Content-Type": mimeTypes.get(path.extname(resolvedPath)) || "application/octet-stream", "Cache-Control": "no-store" });
    response.end(content);
  } catch {
    response.writeHead(404).end("Not found");
  }
});

await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const address = server.address();
const baseUrl = `http://127.0.0.1:${address.port}`;
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

async function noHorizontalOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth }));
  assert(dimensions.scrollWidth <= dimensions.clientWidth + 1, `${label} has horizontal overflow: ${JSON.stringify(dimensions)}`);
}

async function assertTouchTargets(page) {
  const undersized = await page.$$eval(
    ".hero-actions button, .hero-actions a, .audience-tabs button, .interest-form input:not([type=radio]):not([type=checkbox]), .interest-form select, .interest-form button, .menu-button, .mobile-conversion-bar a",
    (controls) => controls.filter((control) => control.getClientRects().length > 0).map((control) => ({ text: control.textContent?.trim(), height: control.getBoundingClientRect().height })).filter((item) => item.height < 47.5),
  );
  assert.deepEqual(undersized, [], `mobile primary controls must be at least 48px tall: ${JSON.stringify(undersized)}`);
}

async function fillLeadForm(page, email) {
  await page.select('[name="role"]', "farmer");
  await page.select('[name="scale"]', "100_1000m2");
  await page.click('[name="pain"][value="watering"]');
  await page.type('[name="email"]', email);
  await page.type('[name="message"]', "離れた畑の水やりと作業計画を確認したい");
  await page.click('[name="consent"]');
}

const consoleErrors = [];
try {
  const desktop = await browser.newPage();
  desktop.on("pageerror", (error) => consoleErrors.push(error.message));
  desktop.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await desktop.evaluateOnNewDocument(() => {
    window.__inasEvents = [];
    window.addEventListener("inas:conversion", (event) => window.__inasEvents.push(event.detail));
  });
  await desktop.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
  const response = await desktop.goto(`${baseUrl}/?utm_source=instagram&utm_medium=paid_social&utm_campaign=early_interest&utm_content=field_status&audience=farmer`, { waitUntil: "networkidle0" });
  assert.equal(response.status(), 200);
  assert.equal(await desktop.$eval("h1", (element) => element.textContent.replace(/\s+/g, " ").trim()), "畑に行く前に、今日やることがわかる。");
  assert.equal(await desktop.$eval(".survey-strip span", (element) => element.textContent.trim()), "開発中");
  assert.equal(await desktop.$eval('[data-audience="farmer"]', (element) => element.getAttribute("aria-selected")), "true");
  assert.equal(await desktop.$eval('[name="role"]', (element) => element.value), "farmer");
  assert.equal(await desktop.$eval(".hero-visual picture img", (image) => image.complete && image.naturalWidth > 100), true);
  assert.equal(await desktop.evaluate(() => performance.getEntriesByType("resource").some((entry) => new URL(entry.name).pathname.endsWith("/assets/hero.webp"))), true, "optimized hero image must be used");
  assert.equal(await desktop.$$eval(".product-feature .screen-frame img", (images) => images.every((image) => image.complete && image.naturalWidth > 100)), true);
  await noHorizontalOverflow(desktop, "desktop");
  const desktopHeroPath = path.join(lpRoot, "artifacts/inas-demand-lp-desktop-hero.png");
  await desktop.screenshot({ path: desktopHeroPath });

  await desktop.click('[data-track="hero_video"]');
  await desktop.waitForSelector("[data-video-dialog][open]");
  assert.equal(await desktop.$eval("[data-video-dialog]", (element) => element.open), true);
  await desktop.click("[data-close-video]");
  await desktop.waitForFunction(() => !document.querySelector("[data-video-dialog]").open);

  await desktop.click('[data-audience="team"]');
  assert.equal(await desktop.$eval('[data-audience-panel="team"]', (element) => element.hidden), false);
  assert.equal(await desktop.$eval('[data-audience-panel="home"]', (element) => element.hidden), true);
  assert.equal(await desktop.$eval('[name="role"]', (element) => element.value), "school", "audience selection must carry into the interest form");

  await desktop.click('[data-track="hero_primary"]');
  const events = await desktop.evaluate(() => window.__inasEvents);
  const heroEvent = events.find((event) => event.event === "cta_click" && event.placement === "hero_primary");
  assert(heroEvent, "hero conversion event was not emitted");
  assert.equal(heroEvent.utm_source, "instagram");
  assert.equal(heroEvent.utm_campaign, "early_interest");

  await fillLeadForm(desktop, "preview@example.com");
  await desktop.click('.interest-form button[type="submit"]');
  await desktop.waitForFunction(() => document.querySelector("[data-form-status]").textContent.includes("受付先が未設定"));
  assert.equal(receivedLeads.length, 0, "unconfigured preview must not send personal data");
  const desktopPath = path.join(lpRoot, "artifacts/inas-demand-lp-desktop.png");
  await desktop.screenshot({ path: desktopPath, fullPage: true });

  const configured = await browser.newPage();
  await configured.setRequestInterception(true);
  configured.on("request", (request) => {
    if (new URL(request.url()).pathname === "/config.js") {
      void request.respond({ status: 200, contentType: "text/javascript", body: `window.INAS_LP_CONFIG=Object.freeze({leadEndpoint:${JSON.stringify(`${baseUrl}/api/leads`)},officialSiteUrl:"https://inas-technologies.com/",githubUrl:"https://github.com/inastechnology",instagramUrl:"https://www.instagram.com/inas_technologies.ja/",privacyUrl:"https://inas-technologies.com/privacy",analyticsMeasurementId:"",metaPixelId:""});` });
    } else void request.continue();
  });
  await configured.goto(`${baseUrl}/?utm_source=google&utm_medium=cpc&utm_campaign=farmer_validation&audience=farmer`, { waitUntil: "networkidle0" });
  await fillLeadForm(configured, "lead@example.com");
  await configured.click('.interest-form button[type="submit"]');
  await configured.waitForFunction(() => document.querySelector("[data-form-status]").textContent.includes("受付が完了"));
  assert.equal(receivedLeads.length, 1);
  assert.equal(receivedLeads[0].email, "lead@example.com");
  assert.equal(receivedLeads[0].pain, "watering");
  assert.equal(receivedLeads[0].attribution.utm_campaign, "farmer_validation");

  const mobile = await browser.newPage();
  mobile.on("pageerror", (error) => consoleErrors.push(error.message));
  mobile.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); });
  await mobile.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await mobile.goto(`${baseUrl}/?utm_source=instagram&utm_campaign=home_validation&audience=home`, { waitUntil: "networkidle0" });
  await noHorizontalOverflow(mobile, "mobile");
  await assertTouchTargets(mobile);
  await mobile.click("[data-menu-button]");
  assert.equal(await mobile.$eval("[data-menu-button]", (element) => element.getAttribute("aria-expanded")), "true");
  assert.equal(await mobile.$eval("[data-mobile-menu]", (element) => element.hidden), false);
  await mobile.keyboard.press("Tab");
  await mobile.click("[data-menu-button]");
  assert.equal(await mobile.$eval("[data-mobile-menu]", (element) => element.hidden), true);
  const mobileHeroPath = path.join(lpRoot, "artifacts/inas-demand-lp-mobile-hero.png");
  await mobile.screenshot({ path: mobileHeroPath });
  const mobilePath = path.join(lpRoot, "artifacts/inas-demand-lp-mobile.png");
  await mobile.screenshot({ path: mobilePath, fullPage: true });
  await mobile.$eval("#interest", (element) => {
    document.documentElement.style.scrollBehavior = "auto";
    element.scrollIntoView({ block: "start", behavior: "auto" });
  });
  await new Promise((resolve) => setTimeout(resolve, 80));
  const mobileFormPath = path.join(lpRoot, "artifacts/inas-demand-lp-mobile-form.png");
  await mobile.screenshot({ path: mobileFormPath });

  assert.deepEqual(consoleErrors, [], `browser console errors: ${JSON.stringify(consoleErrors)}`);
  const report = {
    receivedLead: { role: receivedLeads[0].role, scale: receivedLeads[0].scale, pain: receivedLeads[0].pain, campaign: receivedLeads[0].attribution.utm_campaign },
    screenshots: [desktopHeroPath, desktopPath, mobileHeroPath, mobilePath, mobileFormPath].map((item) => path.basename(item)),
  };
  await writeFile(path.join(lpRoot, "artifacts/smoke-report.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify({ baseUrl, ...report, screenshots: [desktopHeroPath, desktopPath, mobileHeroPath, mobilePath, mobileFormPath] }, null, 2));
} finally {
  await browser.close();
  await new Promise((resolve) => server.close(resolve));
}
