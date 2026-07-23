import { readdir, readFile } from "node:fs/promises";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../src/content/docs/", import.meta.url));
const forbidden = [
  [/CF-Access-Client-Secret\s*[:=]/i, "Cloudflare Access secret"],
  [/BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY/, "private key"],
  [/discord\.gg\/replace-with/i, "placeholder Discord URL in published content"],
];

async function files(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const nested = await Promise.all(entries.map((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  }));
  return nested.flat();
}

let failed = false;
for (const path of await files(root)) {
  if (![".md", ".mdx"].includes(extname(path))) continue;
  const source = await readFile(path, "utf8");
  for (const [pattern, label] of forbidden) {
    if (!pattern.test(source)) continue;
    console.error(`${relative(root, path)}: ${label} must not be published`);
    failed = true;
  }
}

if (failed) process.exit(1);
console.log("Public documentation content check passed.");
