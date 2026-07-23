import assert from "node:assert/strict";
import {
  buildWranglerArguments,
  parseDotEnv,
  resolveDiscordWebhookUrl,
} from "./wrangler-env.mjs";

const parsed = parseDotEnv(`
# comment
DISCORD_WEB_HOOK_URL=https://discord.com/api/webhooks/123/token
QUOTED="value with spaces"
export SINGLE_QUOTED='unchanged'
`);

assert.deepEqual(parsed, {
  DISCORD_WEB_HOOK_URL: "https://discord.com/api/webhooks/123/token",
  QUOTED: "value with spaces",
  SINGLE_QUOTED: "unchanged",
});
assert.equal(
  resolveDiscordWebhookUrl(parsed),
  "https://discord.com/api/webhooks/123/token",
);
assert.equal(
  resolveDiscordWebhookUrl(parsed, {
    DISCORD_WEB_HOOK_URL: "https://discord.com/api/webhooks/456/ci-token",
  }),
  "https://discord.com/api/webhooks/456/ci-token",
);
assert.throws(() => resolveDiscordWebhookUrl({}), /未設定/);
assert.throws(
  () => resolveDiscordWebhookUrl({ DISCORD_WEB_HOOK_URL: "https://example.com/webhook" }),
  /有効なDiscord Webhook URL/,
);
assert.deepEqual(
  buildWranglerArguments("deploy", ["--dry-run"], { secretsFilePath: "/tmp/secrets.json" }),
  ["deploy", "--dry-run", "--secrets-file", "/tmp/secrets.json"],
);
assert.deepEqual(
  buildWranglerArguments("dev", [], { envFilePath: "/tmp/.env" }),
  ["dev", "--env-file", "/tmp/.env"],
);
assert.throws(
  () => buildWranglerArguments("delete", []),
  /未対応/,
);

console.log(JSON.stringify({ ok: true, suite: "wrangler-env" }));
