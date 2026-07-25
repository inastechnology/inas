import { describe, expect, it } from "vitest";

import { validateHubCloudConfig } from "../src/security-config";

describe("Hub Cloud deployment security configuration", () => {
  it("accepts the production security boundary", () => {
    expect(validateHubCloudConfig(validConfig())).toEqual([]);
  });

  it("rejects missing Access and secret controls", () => {
    const config = validConfig();
    config.workers_dev = true;
    config.vars.CLOUDFLARE_ACCESS_TEAM_DOMAIN = "";
    config.vars.CLOUDFLARE_ACCESS_POLICY_AUD = "";
    config.secrets.required = [];

    expect(validateHubCloudConfig(config)).toEqual(
      expect.arrayContaining([
        "workers_dev must be false",
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN is not configured",
        "CLOUDFLARE_ACCESS_POLICY_AUD must be the 64-character Access application AUD",
        "secrets.required must contain DIRECTORY_TURSO_AUTH_TOKEN",
        "secrets.required must contain TENANT_CREDENTIAL_MASTER_KEY",
        "secrets.required must contain DISCORD_SECURITY_WEBHOOK_URL",
      ]),
    );
  });

  it("rejects non-Turso database destinations", () => {
    const config = validConfig();
    config.vars.DIRECTORY_TURSO_DATABASE_URL = "libsql://attacker.invalid";

    expect(validateHubCloudConfig(config)).toContain(
      "DIRECTORY_TURSO_DATABASE_URL must be an exact libsql://*.turso.io database origin",
    );
    config.vars.DIRECTORY_TURSO_DATABASE_URL = "libsql://bad..turso.io";
    expect(validateHubCloudConfig(config)).toContain(
      "DIRECTORY_TURSO_DATABASE_URL must be an exact libsql://*.turso.io database origin",
    );
  });
});

function validConfig() {
  return {
    workers_dev: false,
    preview_urls: false,
    routes: [
      {
        pattern: "cloud-hub.inas-technologies.com",
        custom_domain: true,
      },
    ],
    assets: {
      run_worker_first: ["/api/*", "/sync/*", "/healthz"],
    },
    ratelimits: [
      {
        name: "SYNC_NODE_RATE_LIMITER",
        namespace_id: "7319022",
        simple: { limit: 20, period: 60 },
      },
      {
        name: "SYNC_IP_RATE_LIMITER",
        namespace_id: "7319023",
        simple: { limit: 120, period: 60 },
      },
      {
        name: "SECURITY_ALERT_RATE_LIMITER",
        namespace_id: "7319024",
        simple: { limit: 1, period: 60 },
      },
    ],
    secrets: {
      required: [
        "DIRECTORY_TURSO_AUTH_TOKEN",
        "TENANT_CREDENTIAL_MASTER_KEY",
        "DISCORD_SECURITY_WEBHOOK_URL",
      ],
    },
    vars: {
      CLOUD_HUB_PUBLIC_ORIGIN: "https://cloud-hub.inas-technologies.com",
      CLOUDFLARE_ACCESS_TEAM_DOMAIN: "https://ina.cloudflareaccess.com",
      CLOUDFLARE_ACCESS_POLICY_AUD: "a".repeat(64),
      DIRECTORY_TURSO_DATABASE_URL: "libsql://inas-directory-example.turso.io",
    },
  };
}
