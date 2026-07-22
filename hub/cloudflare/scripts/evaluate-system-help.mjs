import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cloudflareDir, manifest, wrangler } from "./system-help-common.mjs";

const evaluation = JSON.parse(readFileSync(resolve(cloudflareDir, "data/system-help-evaluation.json"), "utf8"));
let passed = 0;
const results = [];

for (const testCase of evaluation.cases) {
  const command = wrangler(
    ["ai-search", "search", manifest.instance, "--query", testCase.question, "--max-num-results", "5", "--score-threshold", "0.2", "--json"],
    { capture: true },
  );
  const response = JSON.parse(command.stdout);
  const chunks = response.chunks ?? response.result?.chunks ?? [];
  const combined = chunks.map((chunk) => `${chunk.item?.key ?? ""}\n${chunk.text ?? ""}`).join("\n");
  const sourceMatched = chunks.slice(0, 3).some((chunk) => String(chunk.item?.key ?? "").endsWith(testCase.expected));
  const termsMatched = testCase.must_include.every((term) => combined.includes(term));
  const ok = sourceMatched && termsMatched;
  if (ok) passed += 1;
  results.push({ question: testCase.question, ok, expected: testCase.expected, top_sources: chunks.slice(0, 3).map((chunk) => chunk.item?.key ?? ""), terms_matched: termsMatched });
}

console.log(JSON.stringify({ passed, total: evaluation.cases.length, results }, null, 2));
if (passed !== evaluation.cases.length) process.exitCode = 1;
