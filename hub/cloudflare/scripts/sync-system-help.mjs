import { bucket, validateDocuments, wrangler } from "./system-help-common.mjs";

const documents = validateDocuments();
const dryRun = process.argv.includes("--dry-run");

for (const document of documents) {
  if (!dryRun) {
    wrangler(["r2", "object", "put", `${bucket}/${document.key}`, "--file", document.path, "--content-type", "text/markdown; charset=utf-8", "--remote"]);
  }
  console.log(`${dryRun ? "validated" : "uploaded"}: ${document.key} (${Buffer.byteLength(document.content)} bytes)`);
}
