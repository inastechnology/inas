import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const locale = process.env.DEMO_VIDEO_LOCALE || "ja";
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const tourPath = path.join(scriptDir, "demo-video/tour.json");
const tour = JSON.parse(await readFile(tourPath, "utf8"));
const copy = tour.locales[locale];
assert(copy, `unsupported DEMO_VIDEO_LOCALE: ${locale}`);

const fps = Number(tour.fps || 10);
const workDir = path.resolve(process.env.DEMO_VIDEO_WORK_DIR || "/tmp/inas-demo-video");
const outputPath = path.resolve(
  process.env.DEMO_VIDEO_OUTPUT || path.join(workDir, `demo-${locale}-silent.mp4`),
);
const posterPath = path.resolve(
  process.env.DEMO_VIDEO_POSTER || path.join(workDir, `demo-${locale}-poster.jpg`),
);
const timelinePath = path.resolve(
  process.env.DEMO_VIDEO_TIMELINE || path.join(workDir, `demo-${locale}-timeline.json`),
);
const frameDir = await mkdtemp(path.join(os.tmpdir(), `ina-app-demo-${locale}-`));
await mkdir(path.dirname(outputPath), { recursive: true });
await mkdir(path.dirname(posterPath), { recursive: true });
await mkdir(path.dirname(timelinePath), { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });

let frameNumber = 0;
const timeline = [];
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const frameName = () => path.join(frameDir, `frame-${String(frameNumber++).padStart(5, "0")}.jpg`);

async function hold(seconds) {
  const count = Math.max(1, Math.round(seconds * fps));
  const image = await page.screenshot({ type: "jpeg", quality: 92, fullPage: false });
  for (let index = 0; index < count; index += 1) await writeFile(frameName(), image);
}

async function prepareScene() {
  await page.evaluate(({ selectedLocale }) => {
    document.documentElement.style.scrollBehavior = "auto";
    document.documentElement.lang = selectedLocale;
    const style = document.createElement("style");
    style.id = "ina-video-style";
    style.textContent = `
      *, *::before, *::after { animation-duration: 0s !important; transition-duration: 0s !important; }
      .ina-video-focus {
        position: relative !important;
        z-index: 9996 !important;
        outline: 5px solid rgba(31, 122, 86, .78) !important;
        outline-offset: 6px !important;
        box-shadow: 0 0 0 9999px rgba(15, 31, 24, .19), 0 18px 55px rgba(14, 55, 39, .24) !important;
      }
      #ina-video-caption {
        position: fixed; left: 42px; bottom: 34px; z-index: 10001;
        width: min(790px, calc(100vw - 84px)); padding: 17px 22px 19px;
        color: #f8fff9; background: rgba(12, 48, 36, .95);
        border: 1px solid rgba(191, 229, 205, .65); border-radius: 16px;
        box-shadow: 0 18px 55px rgba(0, 0, 0, .28);
        font-family: "Noto Sans CJK JP", "Noto Sans JP", sans-serif;
      }
      #ina-video-caption small { display: block; margin-bottom: 5px; color: #bfeecf; font-size: 15px; font-weight: 800; letter-spacing: .09em; }
      #ina-video-caption strong { display: block; font-size: 28px; line-height: 1.27; letter-spacing: .005em; }
      #ina-video-caption span { display: block; margin-top: 7px; color: #e2f2e8; font-size: 16px; line-height: 1.45; }
      html[lang="en"] #ina-video-caption strong { font-size: 26px; }
      html[lang="en"] #ina-video-caption span { font-size: 15px; }
      #ina-video-pointer {
        position: fixed; left: 50%; top: 50%; z-index: 10003; width: 30px; height: 30px;
        pointer-events: none; transform: translate(-4px, -4px);
      }
      #ina-video-pointer::before { content: ''; display: block; width: 18px; height: 25px; background: #fff; clip-path: polygon(0 0, 0 100%, 28% 73%, 47% 100%, 65% 89%, 47% 63%, 82% 62%); filter: drop-shadow(0 2px 2px rgba(0,0,0,.55)); }
      #ina-video-pointer.click::after { content: ''; position: absolute; left: -13px; top: -13px; width: 42px; height: 42px; border: 3px solid #f5bf5b; border-radius: 50%; }
      #ina-video-card {
        position: fixed; inset: 0; z-index: 10010; display: grid; place-items: center; padding: 80px;
        color: #f7fff8; text-align: center; font-family: "Noto Sans CJK JP", "Noto Sans JP", sans-serif;
        background: radial-gradient(circle at 25% 20%, rgba(113, 181, 119, .42), transparent 34%), linear-gradient(145deg, #0c3327, #195c43 58%, #327553);
      }
      #ina-video-card .eyebrow { color: #b8e6c9; font-size: 18px; font-weight: 800; letter-spacing: .15em; }
      #ina-video-card h1 { max-width: 1160px; margin: 20px auto 16px; font-size: 59px; line-height: 1.18; letter-spacing: .015em; white-space: pre-line; }
      #ina-video-card p { max-width: 980px; margin: 0 auto; color: #e0f2e7; font-size: 24px; line-height: 1.55; }
      #ina-video-card .brand { display: inline-flex; align-items: center; gap: 13px; margin-top: 35px; padding: 11px 20px; border: 1px solid rgba(216, 247, 226, .55); border-radius: 999px; font-size: 20px; font-weight: 800; }
      #ina-video-card .brand::before { content: 'i'; display: grid; place-items: center; width: 32px; height: 32px; border-radius: 10px; color: #174934; background: #d8f0df; font-family: serif; font-style: italic; }
      html[lang="en"] #ina-video-card h1 { font-size: 55px; }
    `;
    document.head.append(style);
    const pointer = document.createElement("div");
    pointer.id = "ina-video-pointer";
    document.body.append(pointer);
  }, { selectedLocale: copy.html_language });
}

async function showCaption(scene) {
  await page.evaluate(({ kicker, title, detail }) => {
    document.querySelector("#ina-video-caption")?.remove();
    const caption = document.createElement("div");
    caption.id = "ina-video-caption";
    const small = document.createElement("small");
    const strong = document.createElement("strong");
    const span = document.createElement("span");
    small.textContent = kicker;
    strong.textContent = title;
    span.textContent = detail;
    caption.append(small, strong, span);
    document.body.append(caption);
  }, scene);
}

async function showCard(scene) {
  await page.evaluate(({ eyebrow, title, detail }) => {
    document.querySelector("#ina-video-card")?.remove();
    document.querySelector("#ina-video-caption")?.remove();
    const card = document.createElement("div");
    card.id = "ina-video-card";
    const content = document.createElement("div");
    const eyebrowNode = document.createElement("div");
    const titleNode = document.createElement("h1");
    const detailNode = document.createElement("p");
    const brandNode = document.createElement("div");
    eyebrowNode.className = "eyebrow";
    brandNode.className = "brand";
    eyebrowNode.textContent = eyebrow;
    titleNode.textContent = title;
    detailNode.textContent = detail;
    brandNode.textContent = "inas app / inas technologies";
    content.append(eyebrowNode, titleNode, detailNode, brandNode);
    card.append(content);
    document.body.append(card);
  }, scene);
}

async function clearCard() {
  await page.evaluate(() => document.querySelector("#ina-video-card")?.remove());
}

async function focus(selector) {
  await page.evaluate((targetSelector) => {
    document.querySelectorAll(".ina-video-focus").forEach((element) => element.classList.remove("ina-video-focus"));
    const target = document.querySelector(targetSelector);
    if (!(target instanceof HTMLElement)) throw new Error(`focus target not found: ${targetSelector}`);
    target.scrollIntoView({ block: "center", inline: "nearest", behavior: "auto" });
    target.classList.add("ina-video-focus");
  }, selector);
  await sleep(250);
}

async function movePointer(selector, click = false) {
  await page.evaluate(({ targetSelector, clickTarget }) => {
    const target = document.querySelector(targetSelector);
    const pointer = document.querySelector("#ina-video-pointer");
    if (!(target instanceof HTMLElement) || !(pointer instanceof HTMLElement)) throw new Error(`pointer target not found: ${targetSelector}`);
    const rect = target.getBoundingClientRect();
    pointer.style.left = `${rect.left + rect.width / 2}px`;
    pointer.style.top = `${rect.top + rect.height / 2}px`;
    pointer.classList.toggle("click", clickTarget);
  }, { targetSelector: selector, clickTarget: click });
  await hold(click ? 0.7 : 0.5);
  if (click) await page.evaluate(() => document.querySelector("#ina-video-pointer")?.classList.remove("click"));
}

async function goto(url, readySelector) {
  const localizedUrl = new URL(url, baseUrl);
  if (locale === "en") localizedUrl.searchParams.set("lang", "en");
  await page.goto(localizedUrl.href, { waitUntil: "networkidle0" });
  await page.waitForSelector(readySelector, { visible: true });
  if (locale === "en") {
    await page.waitForFunction(() => document.documentElement.lang === "en" && document.body.dataset.uiLocaleReady === "true");
    await page.waitForFunction(() => !/[\u3040-\u30ff\u3400-\u9fff]/.test(document.body.innerText));
  }
  await prepareScene();
}

async function recordScene(id, render) {
  const scene = copy.scenes[id];
  assert(scene, `missing scene copy: ${id}`);
  const startFrame = frameNumber;
  await render(scene);
  const capturedSeconds = (frameNumber - startFrame) / fps;
  const remainingSeconds = scene.duration_seconds - capturedSeconds;
  assert(remainingSeconds >= -0.001, `${id} captured ${capturedSeconds}s before its ${scene.duration_seconds}s hold`);
  if (remainingSeconds > 0.001) await hold(remainingSeconds);
  const endFrame = frameNumber;
  timeline.push({
    id,
    start_frame: startFrame,
    end_frame: endFrame,
    start_seconds: startFrame / fps,
    end_seconds: endFrame / fps,
    duration_seconds: (endFrame - startFrame) / fps,
    narration: scene.narration,
  });
}

try {
  await goto("/fields/demo-strawberry-field", "#field-status-dashboard");
  await recordScene("intro", async (scene) => showCard(scene));
  await clearCard();

  await recordScene("field_status", async (scene) => {
    await showCaption(scene);
    await focus("#field-status-dashboard");
  });

  await recordScene("action_candidates", async (scene) => {
    await showCaption(scene);
    await focus("#field-action-candidates");
  });

  await goto("/fields/demo-strawberry-field/calendar", ".calendar-workspace-tabs");
  await recordScene("work_board", async (scene) => {
    await showCaption(scene);
    await focus(".calendar-kanban");
  });

  await recordScene("member_progress", async (scene) => {
    await showCaption(scene);
    await focus(".member-task-summary");
  });

  const reviewCard = '[data-kanban-status="awaiting_review"] .calendar-kanban-card';
  await recordScene("manager_review", async (scene) => {
    await showCaption(scene);
    await movePointer(reviewCard, true);
    await page.$eval(reviewCard, (card) => card.click());
    await page.waitForSelector(".calendar-action-detail-dialog .manager-review-panel", { visible: true });
    if (locale === "en") {
      await page.waitForFunction(() => {
        const dialog = document.querySelector(".calendar-action-detail-dialog");
        return dialog && !/[\u3040-\u30ff\u3400-\u9fff]/.test(dialog.innerText);
      });
    }
    await focus(".calendar-action-detail-dialog .manager-review-panel");
  });
  await page.$eval('.calendar-action-detail-dialog [data-calendar-dialog-close]', (button) => button.click());
  await page.waitForFunction(() => !document.querySelector(".calendar-action-detail-dialog"));
  await page.waitForSelector(".gantt-chart", { visible: true });
  await recordScene("crop_plan", async (scene) => {
    await showCaption(scene);
    await focus(".gantt-chart");
  });

  await goto("/mqtt-devices/INADS-DEMO-WTR-001?tab=overview", ".priority-panel");
  await recordScene("irrigation_next", async (scene) => {
    await showCaption(scene);
    await focus(".priority-panel .metrics");
  });

  await recordScene("device_wake", async (scene) => {
    await showCaption(scene);
    await focus("#tab-overview .compact-grid");
  });

  await goto("/mqtt-devices/INADS-DEMO-WTR-001?tab=settings", "#watering-schedules");
  await recordScene("irrigation_schedule", async (scene) => {
    await showCaption(scene);
    await focus("#watering-schedules");
  });

  await recordScene("outro", async (scene) => showCard(scene));

  assert.equal(browserErrors.length, 0, `browser errors:\n${browserErrors.join("\n")}`);
} finally {
  await browser.close();
}

const expectedFrames = Object.values(copy.scenes).reduce(
  (total, scene) => total + Math.round(scene.duration_seconds * fps),
  0,
);
assert.equal(frameNumber, expectedFrames, `captured ${frameNumber} frames; expected ${expectedFrames}`);

const ffmpeg = spawnSync(
  "ffmpeg",
  [
    "-y",
    "-hide_banner",
    "-loglevel", "warning",
    "-framerate", String(fps),
    "-i", path.join(frameDir, "frame-%05d.jpg"),
    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-movflags", "+faststart",
    "-an",
    outputPath,
  ],
  { encoding: "utf8" },
);
if (ffmpeg.status !== 0) throw new Error(`ffmpeg failed:\n${ffmpeg.stderr}`);

const poster = spawnSync(
  "ffmpeg",
  ["-y", "-hide_banner", "-loglevel", "warning", "-ss", "1.5", "-i", outputPath, "-frames:v", "1", "-q:v", "2", posterPath],
  { encoding: "utf8" },
);
if (poster.status !== 0) throw new Error(`poster generation failed:\n${poster.stderr}`);

const timelineDocument = {
  version: 1,
  locale,
  fps,
  total_frames: frameNumber,
  duration_seconds: frameNumber / fps,
  source: baseUrl,
  scenes: timeline,
};
await writeFile(timelinePath, `${JSON.stringify(timelineDocument, null, 2)}\n`);
if (process.env.DEMO_VIDEO_KEEP_FRAMES !== "1") await rm(frameDir, { recursive: true, force: true });

console.log(JSON.stringify({ locale, outputPath, posterPath, timelinePath, frames: frameNumber, fps }, null, 2));
