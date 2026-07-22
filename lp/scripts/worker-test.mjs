import assert from "node:assert/strict";
import worker from "../worker.js";

const inserted = [];
const pending = [];
const db = {
  prepare(sql) {
    return {
      bind(...values) {
        return {
          async run() {
            if (sql.includes("INSERT INTO leads")) inserted.push(values);
            return { success: true };
          },
        };
      },
    };
  },
};
const env = {
  LEADS_DB: db,
  LEAD_RETENTION_DAYS: "365",
  LEAD_RATE_LIMITER: { async limit() { return { success: true }; } },
};
const ctx = { waitUntil(promise) { pending.push(promise); } };
const validPayload = {
  role: "farmer",
  scale: "100_1000m2",
  pain: "watering",
  email: "grower@example.com",
  message: "離れた畑を確認したい",
  website: "",
  consent: true,
  audience: "farmer",
  attribution: { utm_source: "instagram", ignored: "discard-me" },
  source: "inas-demand-validation-lp",
};

function request(payload = validPayload, options = {}) {
  return new Request("https://inas-technologies.com/app/api/leads", {
    method: options.method || "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: options.origin || "https://inas-technologies.com",
      "CF-Connecting-IP": "203.0.113.10",
    },
    body: options.method === "GET" ? undefined : JSON.stringify(payload),
  });
}

const success = await worker.fetch(request(), env, ctx);
assert.equal(success.status, 201);
assert.equal(inserted.length, 1);
assert.equal(inserted[0][1], "farmer");
assert.equal(inserted[0][4], "grower@example.com");
assert.equal(inserted[0][7], JSON.stringify({ utm_source: "instagram" }));

const invalid = await worker.fetch(request({ ...validPayload, consent: false }), env, ctx);
assert.equal(invalid.status, 400);

const bot = await worker.fetch(request({ ...validPayload, website: "https://spam.example" }), env, ctx);
assert.equal(bot.status, 202);
assert.equal(inserted.length, 1);

const wrongOrigin = await worker.fetch(request(validPayload, { origin: "https://example.com" }), env, ctx);
assert.equal(wrongOrigin.status, 403);

const wrongMethod = await worker.fetch(request(validPayload, { method: "GET" }), env, ctx);
assert.equal(wrongMethod.status, 405);

const appRedirect = await worker.fetch(new Request("https://inas-technologies.com/app?utm_source=launch"), env, ctx);
assert.equal(appRedirect.status, 308);
assert.equal(appRedirect.headers.get("Location"), "https://inas-technologies.com/app/?utm_source=launch");

await Promise.all(pending);
console.log(JSON.stringify({ ok: true, inserted: inserted.length }));
