import assert from "node:assert/strict";
import worker from "../worker.js";

const inserted = [];
const sentEmails = [];
const issuedInvites = [];
const webhookRequests = [];
const pending = [];
const originalFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = typeof input === "string" ? input : input.url;
  if (url.startsWith("https://discord.com/api/webhooks/")) {
    webhookRequests.push({
      url,
      method: init?.method,
      body: JSON.parse(String(init?.body || "{}")),
    });
    return new Response(null, { status: 204 });
  }
  return originalFetch(input, init);
};
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
  DISCORD_INVITES: {
    async createInvite(options) {
      issuedInvites.push(options);
      return {
        code: "test-code",
        url: "https://discord.gg/test-code",
        expiresAt: "2026-07-24T00:00:00.000Z",
        maxUses: 1,
      };
    },
  },
  LEAD_EMAIL: {
    async send(message) {
      sentEmails.push(message);
      return { messageId: "test-message-id" };
    },
  },
  LEAD_EMAIL_FROM: "notifications@inas-technologies.com",
  DISCORD_WEB_HOOK_URL: "https://discord.com/api/webhooks/123/test-token",
};
const ctx = { waitUntil(promise) { pending.push(promise); } };
const validPayload = {
  role: "farmer",
  scale: "100_1000m2",
  pain: "watering",
  email: "Grower@Example.COM",
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
assert.equal(inserted[0][4], "Grower@Example.COM");
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
assert.equal(sentEmails.length, 1);
assert.equal(issuedInvites.length, 1);
assert.deepEqual(issuedInvites[0], {
  subjectId: "e4925d268d92cb1a402d68bf5aedc0b3c11f27c207010fac317703b825e4fcb1",
  maxAgeSeconds: 86_400,
  maxUses: 1,
});
assert.equal(sentEmails[0].to, "Grower@Example.COM");
assert.match(sentEmails[0].subject, /Discordコミュニティ/);
assert.match(sentEmails[0].text, /https:\/\/discord\.gg\/test-code/);
assert.doesNotMatch(sentEmails[0].text, /離れた畑を確認したい/);

const inviteFailure = await worker.fetch(
  request({ ...validPayload, email: "invite-failure@example.com" }),
  {
    ...env,
    DISCORD_INVITES: {
      async createInvite() {
        const error = new Error("Discord API error");
        error.status = 403;
        throw error;
      },
    },
  },
  { waitUntil() {} },
);
assert.equal(inviteFailure.status, 502);
assert.equal(webhookRequests.length, 1);
assert.equal(webhookRequests[0].method, "POST");
assert.match(webhookRequests[0].body.content, /invite_issue/);
assert.match(webhookRequests[0].body.content, /http_403/);
assert.doesNotMatch(webhookRequests[0].body.content, /invite-failure@example\.com/);
assert.doesNotMatch(webhookRequests[0].body.content, /discord\.gg/);
assert.deepEqual(webhookRequests[0].body.allowed_mentions, { parse: [] });

const deliveryFailure = await worker.fetch(
  request({ ...validPayload, email: "delivery-failure@example.com" }),
  {
    ...env,
    LEAD_EMAIL: {
      async send(message) {
        if (message.to === "delivery-failure@example.com") {
          const error = new Error("Recipient rejected");
          error.code = "E_DELIVERY_FAILED";
          throw error;
        }
        throw new Error("unexpected recipient");
      },
    },
  },
  { waitUntil() {} },
);
assert.equal(deliveryFailure.status, 502);
assert.equal(webhookRequests.length, 2);
assert.match(webhookRequests[1].body.content, /invite_email/);
assert.match(webhookRequests[1].body.content, /E_DELIVERY_FAILED/);
assert.doesNotMatch(webhookRequests[1].body.content, /delivery-failure@example\.com/);
assert.doesNotMatch(webhookRequests[1].body.content, /discord\.gg/);

globalThis.fetch = originalFetch;
console.log(JSON.stringify({ ok: true, inserted: inserted.length }));
