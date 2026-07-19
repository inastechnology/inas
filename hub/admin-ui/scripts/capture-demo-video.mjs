import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { spawnSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const baseUrl = process.env.HUB_URL || "http://127.0.0.1:39251";
const fps = 10;
const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const outputPath = path.resolve(
  process.env.DEMO_VIDEO_OUTPUT || path.join(scriptDir, "../../doc/jp/assets/inas-app-demo.mp4"),
);
const posterPath = path.resolve(
  process.env.DEMO_VIDEO_POSTER || path.join(scriptDir, "../../doc/jp/assets/inas-app-demo-poster.jpg"),
);
const frameDir = await mkdtemp(path.join(os.tmpdir(), "ina-app-demo-video-"));
await mkdir(path.dirname(outputPath), { recursive: true });

const browser = await puppeteer.launch({
  executablePath: process.env.CHROME_EXECUTABLE || "/usr/bin/google-chrome",
  headless: true,
  args: ["--no-sandbox", "--disable-dev-shm-usage", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });

let frameNumber = 0;
const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") browserErrors.push(message.text());
});

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));
const frameName = () => path.join(frameDir, `frame-${String(frameNumber++).padStart(5, "0")}.jpg`);

async function captureFrame() {
  const image = await page.screenshot({ type: "jpeg", quality: 88, fullPage: false });
  await writeFile(frameName(), image);
}

async function hold(seconds) {
  const count = Math.max(1, Math.round(seconds * fps));
  const image = await page.screenshot({ type: "jpeg", quality: 88, fullPage: false });
  for (let index = 0; index < count; index += 1) {
    await writeFile(frameName(), image);
  }
}

async function prepareScene() {
  await page.evaluate(() => {
    document.documentElement.style.scrollBehavior = "smooth";
    const style = document.createElement("style");
    style.id = "ina-video-style";
    style.textContent = `
      .ina-video-focus {
        position: relative !important;
        z-index: 9996 !important;
        outline: 5px solid rgba(31, 122, 86, .72) !important;
        outline-offset: 6px !important;
        box-shadow: 0 0 0 9999px rgba(15, 31, 24, .18), 0 18px 55px rgba(14, 55, 39, .22) !important;
        transition: outline-color .25s ease, transform .25s ease !important;
      }
      #ina-video-caption {
        position: fixed; left: 42px; bottom: 34px; z-index: 10001;
        width: min(720px, calc(100vw - 84px)); padding: 18px 22px 20px;
        color: #f8fff9; background: rgba(15, 52, 39, .94);
        border: 1px solid rgba(191, 229, 205, .62); border-radius: 16px;
        box-shadow: 0 18px 55px rgba(0, 0, 0, .25); font-family: sans-serif;
      }
      #ina-video-caption small { display: block; margin-bottom: 5px; color: #aee5c4; font-size: 16px; font-weight: 800; letter-spacing: .08em; }
      #ina-video-caption strong { display: block; font-size: 29px; line-height: 1.28; letter-spacing: .01em; }
      #ina-video-caption span { display: block; margin-top: 7px; color: #e2f2e8; font-size: 17px; line-height: 1.45; }
      #ina-video-pointer {
        position: fixed; left: 50%; top: 50%; z-index: 10003; width: 30px; height: 30px;
        pointer-events: none; transform: translate(-4px, -4px); transition: left .28s ease, top .28s ease;
      }
      #ina-video-pointer::before { content: ''; display: block; width: 18px; height: 25px; background: #fff; clip-path: polygon(0 0, 0 100%, 28% 73%, 47% 100%, 65% 89%, 47% 63%, 82% 62%); filter: drop-shadow(0 2px 2px rgba(0,0,0,.55)); }
      #ina-video-pointer.click::after { content: ''; position: absolute; left: -13px; top: -13px; width: 42px; height: 42px; border: 3px solid #f5bf5b; border-radius: 50%; animation: ina-click .55s ease-out; }
      @keyframes ina-click { from { transform: scale(.3); opacity: 1; } to { transform: scale(1.35); opacity: 0; } }
      #ina-video-card {
        position: fixed; inset: 0; z-index: 10010; display: grid; place-items: center; padding: 80px;
        color: #f7fff8; text-align: center; font-family: sans-serif;
        background: radial-gradient(circle at 25% 20%, rgba(113, 181, 119, .42), transparent 34%), linear-gradient(145deg, #0c3327, #195c43 58%, #327553);
      }
      #ina-video-card .eyebrow { color: #b8e6c9; font-size: 19px; font-weight: 800; letter-spacing: .15em; }
      #ina-video-card h1 { max-width: 1120px; margin: 20px auto 16px; font-size: 61px; line-height: 1.18; letter-spacing: .02em; }
      #ina-video-card p { max-width: 980px; margin: 0 auto; color: #e0f2e7; font-size: 25px; line-height: 1.55; }
      #ina-video-card .brand { display: inline-flex; align-items: center; gap: 13px; margin-top: 35px; padding: 11px 20px; border: 1px solid rgba(216, 247, 226, .55); border-radius: 999px; font-size: 20px; font-weight: 800; }
      #ina-video-card .brand::before { content: 'i'; display: grid; place-items: center; width: 32px; height: 32px; border-radius: 10px; color: #174934; background: #d8f0df; font-family: serif; font-style: italic; }
    `;
    document.head.append(style);
    const pointer = document.createElement("div");
    pointer.id = "ina-video-pointer";
    document.body.append(pointer);
  });
}

async function showCaption(kicker, title, detail) {
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
  }, { kicker, title, detail });
}

async function showCard({ eyebrow, title, detail, brand = "inas app by inas technologies" }) {
  await page.evaluate(({ eyebrow, title, detail, brand }) => {
    document.querySelector("#ina-video-card")?.remove();
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
    brandNode.textContent = brand;
    content.append(eyebrowNode, titleNode, detailNode, brandNode);
    card.append(content);
    document.body.append(card);
  }, { eyebrow, title, detail, brand });
}

async function clearCard() {
  await page.evaluate(() => document.querySelector("#ina-video-card")?.remove());
}

async function focus(selector) {
  await page.evaluate((targetSelector) => {
    document.querySelectorAll(".ina-video-focus").forEach((element) => element.classList.remove("ina-video-focus"));
    const target = document.querySelector(targetSelector);
    if (!(target instanceof HTMLElement)) throw new Error(`focus target not found: ${targetSelector}`);
    target.scrollIntoView({ block: "center", behavior: "smooth" });
    target.classList.add("ina-video-focus");
  }, selector);
  await sleep(450);
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
  await page.goto(`${baseUrl}${url}`, { waitUntil: "networkidle0" });
  await page.waitForSelector(readySelector, { visible: true });
  await prepareScene();
}

try {
  await goto("/fields/demo-strawberry-field", "#field-status-dashboard");
  await showCard({
    eyebrow: "畑の『いま』から、次の一手まで",
    title: "栽培と設備を、ひとつの画面で。",
    detail: "計測・作業・年間計画をつなぎ、初心者にも分かる言葉で農作業を支えます。",
  });
  await hold(2.8);
  await clearCard();

  await showCaption("STEP 1 / 見る", "圃場の状態を、ひと目で把握", "土壌水分・湿度・光の状態を、作物の目標範囲と並べて確認できます。");
  await focus("#field-status-dashboard");
  await hold(3.2);

  await showCaption("STEP 2 / 判断する", "計測値を、具体的な作業へ", "今やるべき作業と理由を優先順に表示。迷ったら、カードから詳しい判断条件を開きます。");
  await focus("#field-action-candidates");
  await hold(3.4);

  await goto("/fields/demo-strawberry-field/calendar", ".calendar-workspace-tabs");
  await showCaption("STEP 3 / 整理する", "圃場全体の作業を、状態別に管理", "未完了・作業中・完了を横断して、日付や作物、キーワードで絞り込めます。");
  await focus(".calendar-kanban");
  await hold(3.2);

  const plannedCard = '[data-kanban-status="planned"] .calendar-kanban-card';
  await movePointer(plannedCard, true);
  await page.click(plannedCard);
  await page.waitForSelector(".calendar-action-detail-dialog .work-guidance", { visible: true });
  await showCaption("STEP 4 / 実行する", "作業の開始条件・手順・見送り条件まで", "専門知識がなくても、確認する順番と完了の目安を追いながら作業できます。");
  await focus(".calendar-action-detail-dialog .work-guidance");
  await hold(3.5);
  await page.click(".calendar-action-detail-dialog > header .icon-button");

  await page.$$eval(".calendar-workspace-tabs button", (buttons) => {
    const button = buttons.find((item) => item.textContent?.includes("作物別の栽培計画"));
    if (!(button instanceof HTMLButtonElement)) throw new Error("crop plan tab was not found");
    button.click();
  });
  await page.waitForSelector(".gantt-chart", { visible: true });
  await showCaption("STEP 5 / 見通す", "年間の作業と収穫期を、一本の時間軸に", "受粉、施肥、季節管理、収穫までを俯瞰し、計画変更も比較しながら反映できます。");
  await focus(".gantt-chart");
  await hold(4.0);

  await goto("/mqtt-devices/INADS-DEMO-WTR-001?tab=overview", ".priority-panel");
  await showCaption("STEP 6 / つなぐ", "設備の状態から、次の操作へ最短で", "次回の水やりと現在値を確認し、その場から水やりルートを組み替えられます。");
  await focus(".priority-panel");
  await hold(2.8);

  await goto("/mqtt-devices/INADS-DEMO-WTR-001?tab=settings", "#open-output-settings");
  await showCaption("STEP 6 / つなぐ", "現在の水やりルートを、その場で編集", "設定画面を探し回らず、接続図を選んで設備の組み合わせを変更できます。");
  await focus("#open-output-settings");
  await hold(2.4);
  await movePointer("#open-output-settings", true);
  await page.$eval("#open-output-settings", (trigger) => trigger.click());
  await page.waitForSelector("#output-settings-dialog[open]", { visible: true, timeout: 5000 });
  await showCaption("ゲームのように設定", "使う設備を絵から選ぶと、配線がつながる", "難しい電子回路用語を意識せず、水やり設備と接続先を視覚的に設定できます。");
  await focus("#mosfet-switch-editor");
  await hold(4.0);

  await page.evaluate(() => {
    const dialog = document.querySelector("#output-settings-dialog");
    if (dialog instanceof HTMLDialogElement && dialog.open) dialog.close();
  });
  await showCard({
    eyebrow: "OPEN SOURCE AGRICULTURE PLATFORM",
    title: "小さく始めて、農場と一緒に育てる。",
    detail: "オープンソースで自作可能。完成済みのHubや潅水デバイスも選べます。",
    brand: "inas app / inas technologies",
  });
  await hold(3.2);

  assert.equal(browserErrors.length, 0, `browser errors:\n${browserErrors.join("\n")}`);
} finally {
  await browser.close();
}

assert(frameNumber > 200, `not enough video frames were captured: ${frameNumber}`);
const ffmpeg = spawnSync(
  "ffmpeg",
  [
    "-y",
    "-framerate", String(fps),
    "-i", path.join(frameDir, "frame-%05d.jpg"),
    "-vf", "scale=1920:1080:flags=lanczos,format=yuv420p",
    "-r", "30",
    "-c:v", "libx264",
    "-preset", "medium",
    "-crf", "18",
    "-movflags", "+faststart",
    outputPath,
  ],
  { encoding: "utf8" },
);
if (ffmpeg.status !== 0) throw new Error(`ffmpeg failed:\n${ffmpeg.stderr}`);

const poster = spawnSync(
  "ffmpeg",
  ["-y", "-ss", "1.2", "-i", outputPath, "-frames:v", "1", "-q:v", "2", posterPath],
  { encoding: "utf8" },
);
if (poster.status !== 0) throw new Error(`poster generation failed:\n${poster.stderr}`);

console.log(JSON.stringify({ outputPath, posterPath, frameDir, frames: frameNumber, fps }, null, 2));
