import { bucket, manifest, validateDocuments, wrangler } from "./system-help-common.mjs";

const documents = validateDocuments();
const dryRun = process.argv.includes("--dry-run");
const force = process.argv.includes("--force");
const triggerIndex = process.argv.includes("--trigger-index");
let uploaded = 0;
let unchanged = 0;

for (const document of documents) {
  if (dryRun) {
    console.log(`validated: ${document.key} (${Buffer.byteLength(document.content)} bytes)`);
    continue;
  }

  let contentMatches = false;
  if (!force) {
    const remote = wrangler(["r2", "object", "get", `${bucket}/${document.key}`, "--pipe", "--remote"], { capture: true, allowFailure: true });
    if (remote.status === 0) {
      contentMatches = remote.stdout === document.content;
    } else {
      const detail = `${remote.stderr ?? ""}\n${remote.stdout ?? ""}`.trim();
      if (!/(NoSuchKey|not found|does not exist|404)/i.test(detail)) {
        throw new Error(`failed to compare remote document ${document.key}${detail ? `: ${detail}` : ""}`);
      }
    }
  }

  if (contentMatches) {
    unchanged += 1;
    console.log(`unchanged: ${document.key}`);
    continue;
  }

  wrangler([
    "r2",
    "object",
    "put",
    `${bucket}/${document.key}`,
    "--file",
    document.path,
    "--content-type",
    "text/markdown; charset=utf-8",
    "--remote",
    "--force",
  ]);
  uploaded += 1;
  console.log(`uploaded: ${document.key} (${Buffer.byteLength(document.content)} bytes)`);
}

if (!dryRun && triggerIndex && uploaded > 0) {
  wrangler(["ai-search", "jobs", "create", manifest.instance]);
  console.log(`AI Search incremental indexing requested: instance=${manifest.instance}`);
} else if (!dryRun && triggerIndex) {
  console.log("AI Search indexing was not requested because no document changed.");
}

if (!dryRun) {
  console.log(`System help sync complete: uploaded=${uploaded}, unchanged=${unchanged}, total=${documents.length}`);
}
