import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const fixturePath = fileURLToPath(new URL("../fixtures/community-extension.json", import.meta.url));
const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});
const page = await browser.newPage();
const browserErrors = [];
let aiAuditRequests = 0;
page.on("request", (request) => {
  if (request.url().includes("/local/api/extensions/reviews/") && request.url().endsWith("/ai-audit")) aiAuditRequests += 1;
});
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

try {
  await page.setViewport({ width: 1360, height: 920, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/settings/extensions`, { waitUntil: "networkidle0" });
  assert.equal(await page.$eval("h1", (heading) => heading.textContent?.trim()), "追加機能");
  assert.match(await page.$eval(".hero", (hero) => hero.textContent || ""), /AI監査は自動では始まりません/);
  assert.equal(await page.$eval("#static-review-button", (button) => button.getBoundingClientRect().height >= 48), true);
  await page.screenshot({ path: "/tmp/ina-extension-management.png", fullPage: true });

  const input = await page.$("#extension-file");
  await input.uploadFile(fixturePath);
  await page.click("#static-review-button");
  await page.waitForSelector("#review-dialog[open]");
  assert.equal(aiAuditRequests, 0, "upload and static review must not call the AI audit API");
  assert.equal(await page.$eval("#install-button", (button) => button.disabled), true);
  assert.match(await page.$eval("#review-dialog", (dialog) => dialog.innerText || ""), /実行コードなし/);
  assert.match(await page.$eval("#review-dialog", (dialog) => dialog.innerText || ""), /提供元\s*未検証/);
  await page.screenshot({ path: "/tmp/ina-extension-static-review.png", fullPage: true });

  await page.click("#open-ai-confirmation");
  await page.waitForSelector("#ai-confirm-dialog[open]");
  assert.equal(aiAuditRequests, 0, "opening the AI preflight dialog must not send data");
  const confirmationText = await page.$eval("#ai-confirm-dialog", (dialog) => dialog.innerText || "");
  assert.match(confirmationText, /送信する: 検証済みの追加機能定義/);
  assert.match(confirmationText, /送信しない: APIキー、DB、機器データ/);
  assert.match(confirmationText, /利用モデル/);
  assert.match(confirmationText, /利用料が発生する場合/);
  await page.screenshot({ path: "/tmp/ina-extension-ai-confirmation.png", fullPage: true });

  await page.click('[data-cancel-ai]');
  await page.waitForFunction(() => !document.querySelector("#ai-confirm-dialog")?.open);
  assert.equal(aiAuditRequests, 0, "cancelling the preflight dialog must send nothing");
  assert.equal(await page.$eval("#install-button", (button) => button.disabled), true);

  await page.click("#open-ai-confirmation");
  await page.click("#confirm-ai-audit");
  await page.waitForFunction(() => !document.querySelector("#ai-confirm-dialog")?.open);
  assert.equal(aiAuditRequests, 1, "AI audit must start only after the explicit confirmation button");
  assert.equal(await page.$eval("#install-button", (button) => button.disabled), false);
  assert.match(await page.$eval("#ai-summary", (element) => element.textContent || ""), /AIが未設定|AI監査を完了できなかった/);
  await page.screenshot({ path: "/tmp/ina-extension-ai-result.png", fullPage: true });
  await page.click('[data-close-review]');

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.goto(`${baseUrl}/settings/extensions`, { waitUntil: "networkidle0" });
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    true,
    "extension management must not overflow on mobile",
  );
  await page.screenshot({ path: "/tmp/ina-extension-management-mobile.png", fullPage: true });
  const mobileInput = await page.$("#extension-file");
  await mobileInput.uploadFile(fixturePath);
  await page.click("#static-review-button");
  await page.waitForSelector("#review-dialog[open]");
  await page.click("#open-ai-confirmation");
  await page.waitForSelector("#ai-confirm-dialog[open]");
  assert.equal(aiAuditRequests, 1, "opening the mobile confirmation must not send data");
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth),
    true,
    "AI confirmation must not overflow on mobile",
  );
  await page.screenshot({ path: "/tmp/ina-extension-ai-confirmation-mobile.png" });
  assert.deepEqual(browserErrors, []);

  process.stdout.write(JSON.stringify({ screenshots: [
    "/tmp/ina-extension-management.png",
    "/tmp/ina-extension-static-review.png",
    "/tmp/ina-extension-ai-confirmation.png",
    "/tmp/ina-extension-ai-result.png",
    "/tmp/ina-extension-management-mobile.png",
    "/tmp/ina-extension-ai-confirmation-mobile.png",
  ] }, null, 2) + "\n");
} finally {
  await browser.close();
}
