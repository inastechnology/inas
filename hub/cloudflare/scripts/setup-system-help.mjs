import { bucket, manifest, validateDocuments, wrangler } from "./system-help-common.mjs";

validateDocuments();

const bucketInfo = wrangler(["r2", "bucket", "info", bucket, "--json"], { capture: true, allowFailure: true });
if (bucketInfo.status !== 0) {
  wrangler(["r2", "bucket", "create", bucket]);
}

const instances = wrangler(["ai-search", "list", "--json"], { capture: true });
const instanceList = JSON.parse(instances.stdout || "[]");
if (!instanceList.some((item) => item.id === manifest.instance || item.name === manifest.instance)) {
  wrangler([
    "ai-search", "create", manifest.instance, "--type", "r2", "--source", bucket,
    "--hybrid-search", "--score-threshold", "0.2", "--max-num-results", "5",
  ]);
}

console.log(`System help resources are ready: bucket=${bucket}, instance=${manifest.instance}`);
