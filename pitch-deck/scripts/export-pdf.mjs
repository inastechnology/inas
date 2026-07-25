import { mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = dirname(here);
const artifactDir = join(root, "artifacts");
const output = process.env.PITCH_PDF || join(artifactDir, "inas-startup-pitch-2026.pdf");
const deckUrl = process.env.DECK_URL || "http://127.0.0.1:4330/pitch-deck/";
const requireFromDocsSite = createRequire(new URL("../../docs-site/package.json", import.meta.url));
const puppeteer = requireFromDocsSite("puppeteer-core");

await mkdir(artifactDir, { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

try {
  const page = await browser.newPage();
  await page.goto(deckUrl, { waitUntil: "networkidle0" });
  await page.emulateMediaType("print");
  await page.pdf({
    path: output,
    width: "13.333333in",
    height: "7.5in",
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: false,
    margin: { top: 0, right: 0, bottom: 0, left: 0 },
  });
  console.log(output);
} finally {
  await browser.close();
}
