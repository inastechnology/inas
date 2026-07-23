import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const lpDirectory = resolve(scriptDirectory, "..");
const supportedCommands = new Set(["deploy", "dev"]);

function unquote(value, lineNumber) {
  if (!value.startsWith('"') && !value.startsWith("'")) {
    return value.replace(/\s+#.*$/, "").trim();
  }

  const quote = value[0];
  if (value.length < 2 || value.at(-1) !== quote) {
    throw new Error(`.env ${lineNumber}行目の引用符が閉じられていません。`);
  }

  const inner = value.slice(1, -1);
  if (quote === "'") return inner;
  return inner
    .replace(/\\n/g, "\n")
    .replace(/\\r/g, "\r")
    .replace(/\\t/g, "\t")
    .replace(/\\"/g, '"')
    .replace(/\\\\/g, "\\");
}

export function parseDotEnv(source) {
  const values = {};

  source.split(/\r?\n/).forEach((rawLine, index) => {
    const lineNumber = index + 1;
    let line = rawLine.trim();
    if (!line || line.startsWith("#")) return;
    if (line.startsWith("export ")) line = line.slice(7).trimStart();

    const separator = line.indexOf("=");
    if (separator < 1) {
      throw new Error(`.env ${lineNumber}行目は KEY=value 形式ではありません。`);
    }

    const key = line.slice(0, separator).trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) {
      throw new Error(`.env ${lineNumber}行目の変数名が不正です。`);
    }

    values[key] = unquote(line.slice(separator + 1).trim(), lineNumber);
  });

  return values;
}

export function resolveDiscordWebhookUrl(fileValues, systemEnvironment = {}) {
  const webhookUrl = String(
    systemEnvironment.DISCORD_WEB_HOOK_URL
      || fileValues.DISCORD_WEB_HOOK_URL
      || "",
  ).trim();

  if (!webhookUrl) {
    throw new Error(
      "DISCORD_WEB_HOOK_URL が未設定です。lp/.env.example を lp/.env にコピーして障害通知先を設定してください。",
    );
  }

  try {
    const parsed = new URL(webhookUrl);
    const validHost = parsed.hostname === "discord.com" || parsed.hostname === "discordapp.com";
    if (
      webhookUrl.length > 2000
      || parsed.protocol !== "https:"
      || !validHost
      || !parsed.pathname.startsWith("/api/webhooks/")
    ) {
      throw new Error("invalid");
    }
  } catch {
    throw new Error("DISCORD_WEB_HOOK_URL に有効なDiscord Webhook URLを設定してください。");
  }

  return webhookUrl;
}

export function buildWranglerArguments(
  command,
  forwardedArguments,
  { envFilePath = "", secretsFilePath = "" } = {},
) {
  if (!supportedCommands.has(command)) {
    throw new Error(`未対応のWranglerコマンドです: ${command || "(未指定)"}`);
  }

  const argumentsList = [command, ...forwardedArguments];
  if (command === "deploy" && secretsFilePath) {
    argumentsList.push("--secrets-file", secretsFilePath);
  }
  if (command === "dev" && envFilePath) {
    argumentsList.push("--env-file", envFilePath);
  }
  return argumentsList;
}

function run() {
  const [command, ...forwardedArguments] = process.argv.slice(2);
  const envPath = resolve(lpDirectory, process.env.LP_ENV_FILE || ".env");
  let fileValues = {};

  try {
    fileValues = parseDotEnv(readFileSync(envPath, "utf8"));
  } catch (error) {
    if (error?.code !== "ENOENT" || !process.env.DISCORD_WEB_HOOK_URL) {
      throw error;
    }
  }

  const webhookUrl = resolveDiscordWebhookUrl(fileValues, process.env);
  const temporaryDirectory = mkdtempSync(join(tmpdir(), "inas-lp-secrets-"));
  const temporaryFile = join(
    temporaryDirectory,
    command === "deploy" ? "secrets.json" : ".env",
  );
  if (command === "deploy") {
    writeFileSync(
      temporaryFile,
      JSON.stringify({ DISCORD_WEB_HOOK_URL: webhookUrl }),
      { encoding: "utf8", mode: 0o600 },
    );
  } else {
    writeFileSync(
      temporaryFile,
      `DISCORD_WEB_HOOK_URL=${JSON.stringify(webhookUrl)}\n`,
      { encoding: "utf8", mode: 0o600 },
    );
  }

  const wranglerArguments = buildWranglerArguments(command, forwardedArguments, {
    envFilePath: command === "dev" ? temporaryFile : "",
    secretsFilePath: command === "deploy" ? temporaryFile : "",
  });
  const executable = resolve(
    lpDirectory,
    "node_modules",
    ".bin",
    process.platform === "win32" ? "wrangler.cmd" : "wrangler",
  );
  if (!existsSync(executable)) {
    rmSync(temporaryDirectory, { recursive: true, force: true });
    throw new Error("Wranglerが見つかりません。lp/ で npm install を実行してください。");
  }

  try {
    const result = spawnSync(executable, wranglerArguments, {
      cwd: lpDirectory,
      env: process.env,
      stdio: "inherit",
    });
    if (result.error) throw result.error;
    process.exitCode = result.status ?? 1;
  } finally {
    rmSync(temporaryDirectory, { recursive: true, force: true });
  }
}

if (fileURLToPath(import.meta.url) === resolve(process.argv[1] || "")) {
  try {
    run();
  } catch (error) {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  }
}
