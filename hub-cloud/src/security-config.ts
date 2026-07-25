import { accessTeamOrigin } from "./access";
import { normalizeTursoDatabaseUrl } from "./database";

export const REQUIRED_WORKER_SECRETS = [
  "DIRECTORY_TURSO_AUTH_TOKEN",
  "TENANT_CREDENTIAL_MASTER_KEY",
  "DISCORD_SECURITY_WEBHOOK_URL",
] as const;

export function validateHubCloudConfig(value: unknown): string[] {
  const errors: string[] = [];
  const config = record(value);
  if (!config) {
    return ["wrangler configuration must be a JSON object"];
  }
  if (config.workers_dev !== false) {
    errors.push("workers_dev must be false");
  }
  if (config.preview_urls !== false) {
    errors.push("preview_urls must be false");
  }

  const routes = Array.isArray(config.routes) ? config.routes : [];
  const customRoutes = routes
    .map(record)
    .filter((route): route is Record<string, unknown> => route !== null);
  if (
    customRoutes.length !== 1 ||
    customRoutes[0]?.pattern !== "cloud-hub.inas-technologies.com" ||
    customRoutes[0]?.custom_domain !== true
  ) {
    errors.push("exactly one custom-domain route for cloud-hub.inas-technologies.com is required");
  }

  const vars = record(config.vars);
  const publicOrigin = stringValue(vars?.CLOUD_HUB_PUBLIC_ORIGIN);
  if (publicOrigin !== "https://cloud-hub.inas-technologies.com") {
    errors.push("CLOUD_HUB_PUBLIC_ORIGIN must be https://cloud-hub.inas-technologies.com");
  }
  const accessTeamDomain = stringValue(vars?.CLOUDFLARE_ACCESS_TEAM_DOMAIN);
  if (!accessTeamDomain) {
    errors.push("CLOUDFLARE_ACCESS_TEAM_DOMAIN is not configured");
  } else {
    try {
      accessTeamOrigin(accessTeamDomain);
    } catch (error) {
      errors.push(message(error));
    }
  }
  if (!/^[a-f0-9]{64}$/.test(stringValue(vars?.CLOUDFLARE_ACCESS_POLICY_AUD))) {
    errors.push("CLOUDFLARE_ACCESS_POLICY_AUD must be the 64-character Access application AUD");
  }
  try {
    normalizeTursoDatabaseUrl(
      stringValue(vars?.DIRECTORY_TURSO_DATABASE_URL),
      "DIRECTORY_TURSO_DATABASE_URL",
    );
  } catch (error) {
    errors.push(message(error));
  }

  const assets = record(config.assets);
  const runWorkerFirst = Array.isArray(assets?.run_worker_first)
    ? assets.run_worker_first
    : [];
  for (const route of ["/api/*", "/sync/*", "/healthz"]) {
    if (!runWorkerFirst.includes(route)) {
      errors.push(`assets.run_worker_first must contain ${route}`);
    }
  }

  const rateLimits = Array.isArray(config.ratelimits) ? config.ratelimits : [];
  validateRateLimit(rateLimits, "SYNC_NODE_RATE_LIMITER", 20, errors);
  validateRateLimit(rateLimits, "SYNC_IP_RATE_LIMITER", 120, errors);
  validateRateLimit(rateLimits, "SECURITY_ALERT_RATE_LIMITER", 1, errors);

  const secrets = record(config.secrets);
  const requiredSecrets = Array.isArray(secrets?.required)
    ? new Set(secrets.required.filter((item): item is string => typeof item === "string"))
    : new Set<string>();
  for (const secret of REQUIRED_WORKER_SECRETS) {
    if (!requiredSecrets.has(secret)) {
      errors.push(`secrets.required must contain ${secret}`);
    }
  }
  return [...new Set(errors)];
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : "invalid configuration";
}

function validateRateLimit(
  values: unknown[],
  name: string,
  limit: number,
  errors: string[],
): void {
  const binding = values.map(record).find((item) => item?.name === name);
  const simple = record(binding?.simple);
  if (
    !binding ||
    !/^[1-9][0-9]*$/.test(stringValue(binding.namespace_id)) ||
    simple?.limit !== limit ||
    simple?.period !== 60
  ) {
    errors.push(`${name} must enforce ${limit} requests per 60 seconds`);
  }
}
