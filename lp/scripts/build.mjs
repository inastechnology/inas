import { cp, mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const lpRoot = path.resolve(scriptDirectory, "..");
const outputRoot = path.join(lpRoot, "dist");
const appOutput = path.join(outputRoot, "app");
const publicFiles = ["index.html", "404.html", "styles.css", "app.js", "config.js"];

await rm(outputRoot, { recursive: true, force: true });
await mkdir(appOutput, { recursive: true });
for (const filename of publicFiles) {
  const source = path.join(lpRoot, filename);
  await stat(source);
  await cp(source, path.join(appOutput, filename));
}
await cp(path.join(lpRoot, "assets"), path.join(appOutput, "assets"), { recursive: true });

console.log(`Built ${appOutput}`);
