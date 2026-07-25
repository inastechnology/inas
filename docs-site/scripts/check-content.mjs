import { access, readdir, readFile } from "node:fs/promises";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/content/docs/", import.meta.url));
const publicRoot = fileURLToPath(new URL("../public/", import.meta.url));
const screenshotRoot = join(publicRoot, "images", "screenshots");
const illustrationRoot = join(publicRoot, "images", "illustrations");
const forbidden = [
  [/CF-Access-Client-Secret\s*[:=]/i, "Cloudflare Access secret"],
  [/BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY/, "private key"],
  [/discord\.gg\/replace-with/i, "placeholder Discord URL in published content"],
];
const generalSetupPages = new Set([
  "index.mdx",
  "start/overview.mdx",
  "start/choose-path.mdx",
  "start/network.mdx",
  "start/provided-hardware.mdx",
  "start/safety.mdx",
  "configure/settings.mdx",
  "configure/fields-devices.mdx",
  "configure/watering.mdx",
]);
const advancedTerms = [
  [/\bmDNS\b/i, "mDNS"],
  [/\bMQTT\b/i, "MQTT"],
  [/\bDHCP\b/i, "DHCP"],
  [/\bSSID\b/i, "SSID"],
  [/\bVLAN\b/i, "VLAN"],
  [/\bhostname\b/i, "hostname"],
  [/\bbroker\b/i, "broker"],
  [/\bsystemd\b/i, "systemd"],
  [/\bMosquitto\b/i, "Mosquitto"],
  [/\bRuntime Config\b/i, "Runtime Config"],
  [/\bCloudflare (?:Access|Tunnel)\b/i, "Cloudflare Access/Tunnel"],
  [/\bOTA\b/i, "OTA"],
  [/\b(?:AP|client) isolation\b/i, "AP/client isolation"],
  [/\bport(?: forward)?\b/i, "port"],
  [/予約IP|IPアドレス|IP address/i, "IP address"],
  [/\.env\b/i, ".env"],
  [/\bSSH\b/i, "SSH"],
  [/\bHTTPS?\b/i, "HTTP"],
  [/\bLAN\b/i, "LAN"],
];
const screenshotReferencePattern = /src=["'](\/images\/screenshots\/[^"'?#]+)["']/g;
const illustrationReferencePattern = /src=["'](\/images\/illustrations\/[^"'?#]+)["']/g;

const visualManualRequirements = new Map([
  ["start/overview.mdx", { steps: 4, prep: false }],
  ["start/network.mdx", { steps: 5, prep: true }],
  ["start/safety.mdx", { steps: 4, prep: true }],
  ["start/quickstart.mdx", { steps: 9, prep: true }],
  ["hub/raspberry-pi.mdx", { steps: 6, prep: true }],
  ["hub/install.mdx", { steps: 6, prep: true }],
  ["hub/cloudflare.mdx", { steps: 5, prep: true }],
  ["hub/update-backup.mdx", { steps: 4, prep: true }],
  ["devices/wtr.mdx", { steps: 6, prep: true }],
  ["configure/fields-devices.mdx", { steps: 6, prep: true }],
  ["configure/watering.mdx", { steps: 6, prep: true }],
]);
const manualStepVisualPattern = /\bvisual:\s*["'][^"']+["']/g;
const visualLayoutRequirements = new Map([
  ["start/provided-hardware.mdx", ["setup-flyer", "setup-flyer__steps", "device-catalog.webp"]],
  ["configure/settings.mdx", ["settings-scope-map", "user-preferences.webp", "watering-settings.webp"]],
  ["technical/architecture.mdx", ["CommunicationRoutes", "SystemComponents"]],
  ["technical/app-settings.mdx", ["app-settings-ai.webp", "app-settings-notifications.webp", "app-settings-instagram.webp", "app-settings-system.webp"]],
]);

async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  }));
  return nested.flat();
}

let failed = false;
const screenshotReferences = new Set();
const illustrationReferences = new Set();
for (const path of await files(root)) {
  if (![".md", ".mdx"].includes(extname(path))) continue;
  const source = await readFile(path, "utf8");
  const contentPath = relative(root, path).replaceAll("\\", "/");
  for (const [pattern, label] of forbidden) {
    if (!pattern.test(source)) continue;
    console.error(`${contentPath}: ${label} must not be published`);
    failed = true;
  }
  if (generalSetupPages.has(contentPath)) {
    for (const [pattern, label] of advancedTerms) {
      if (!pattern.test(source)) continue;
      console.error(`${contentPath}: ${label} belongs in technical documentation, not general setup`);
      failed = true;
    }
  }
  const visualRequirement = visualManualRequirements.get(contentPath);
  if (visualRequirement) {
    const stepVisualCount = [...source.matchAll(manualStepVisualPattern)].length;
    if (stepVisualCount < visualRequirement.steps) {
      console.error(`${contentPath}: expected at least ${visualRequirement.steps} illustrated manual steps, found ${stepVisualCount}`);
      failed = true;
    }
    if (visualRequirement.prep && !source.includes("manual-prep-panel")) {
      console.error(`${contentPath}: procedural guide must include a prominent preparation panel`);
      failed = true;
    }
  }
  const requiredVisualMarkers = visualLayoutRequirements.get(contentPath) || [];
  for (const marker of requiredVisualMarkers) {
    if (source.includes(marker)) continue;
    console.error(`${contentPath}: required visual layout marker is missing: ${marker}`);
    failed = true;
  }
  for (const match of source.matchAll(screenshotReferencePattern)) {
    const publicPath = match[1].slice(1);
    screenshotReferences.add(publicPath);
    try {
      await access(join(publicRoot, publicPath));
    } catch {
      console.error(`${contentPath}: referenced screenshot does not exist: ${match[1]}`);
      failed = true;
    }
  }
  for (const match of source.matchAll(illustrationReferencePattern)) {
    const publicPath = match[1].slice(1);
    illustrationReferences.add(publicPath);
    try {
      await access(join(publicRoot, publicPath));
    } catch {
      console.error(`${contentPath}: referenced illustration does not exist: ${match[1]}`);
      failed = true;
    }
  }
}

for (const name of await readdir(screenshotRoot)) {
  if (extname(name) !== ".webp") continue;
  const publicPath = join("images", "screenshots", name);
  if (screenshotReferences.has(publicPath)) continue;
  console.error(`${publicPath}: generated screenshot is not referenced by public documentation`);
  failed = true;
}

for (const name of await readdir(illustrationRoot)) {
  if (extname(name) !== ".webp") continue;
  const publicPath = join("images", "illustrations", name);
  if (illustrationReferences.has(publicPath)) continue;
  console.error(`${publicPath}: generated illustration is not referenced by public documentation`);
  failed = true;
}

if (failed) process.exit(1);
console.log("Public documentation content check passed.");
