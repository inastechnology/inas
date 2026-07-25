import type { Env } from "./types";

export type SecurityEventKind =
  | "access_authentication_rejected"
  | "node_authentication_rejected"
  | "authorization_rejected"
  | "cross_origin_mutation_rejected"
  | "sync_rate_limit_exceeded"
  | "oversized_request_rejected";

export interface SecurityEventInput {
  kind: SecurityEventKind;
  status: 401 | 403 | 413 | 429;
  authentication: "access" | "node" | "none";
  route: "/api/*" | "/sync/v1/nodes/:nodeId/exchange" | "/";
}

export interface SecurityAuditEvent extends SecurityEventInput {
  event_id: string;
  occurred_at: string;
  service: "inas-hub-cloud";
  method: string;
  cf_ray: string | null;
}

export type SecurityReporter = (
  request: Request,
  env: Env,
  input: SecurityEventInput,
) => Promise<void>;

const DISCORD_WEBHOOK_PATH = /^\/api(?:\/v[0-9]+)?\/webhooks\/[0-9]+\/[A-Za-z0-9._-]+$/;
const SAFE_METHOD = /^(?:GET|HEAD|POST|PUT|PATCH|DELETE|OPTIONS)$/;
const SAFE_RAY_ID = /^[A-Za-z0-9-]{1,64}$/;

export async function reportSecurityEvent(
  request: Request,
  env: Env,
  input: SecurityEventInput,
): Promise<void> {
  const event = createSecurityAuditEvent(request, input);
  console.warn("cloud_hub_security_audit", event);

  let stage = "configuration";
  try {
    const webhookUrl = discordWebhookUrl(env.DISCORD_SECURITY_WEBHOOK_URL);
    if (!env.SECURITY_ALERT_RATE_LIMITER?.limit) {
      console.error("cloud_hub_security_notification_unavailable", {
        event_id: event.event_id,
        reason: "rate_limiter_not_configured",
      });
      return;
    }
    stage = "rate_limit";
    const allowance = await env.SECURITY_ALERT_RATE_LIMITER.limit({
      key: securityAlertRateLimitKey(event),
    });
    if (!allowance.success) {
      console.info("cloud_hub_security_notification_suppressed", {
        event_id: event.event_id,
        kind: event.kind,
        route: event.route,
      });
      return;
    }
    stage = "delivery";
    const response = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(discordPayload(event)),
      redirect: "manual",
    });
    if (!response.ok) {
      console.error("cloud_hub_security_notification_failed", {
        event_id: event.event_id,
        status: response.status,
      });
    }
  } catch (error) {
    console.error("cloud_hub_security_notification_failed", {
      event_id: event.event_id,
      stage,
      reason: error instanceof Error ? error.name : "unknown_error",
    });
  }
}

export function createSecurityAuditEvent(
  request: Request,
  input: SecurityEventInput,
): SecurityAuditEvent {
  const method = request.method.toUpperCase();
  const ray = request.headers.get("CF-Ray")?.trim() ?? "";
  return {
    event_id: crypto.randomUUID(),
    occurred_at: new Date().toISOString(),
    service: "inas-hub-cloud",
    ...input,
    method: SAFE_METHOD.test(method) ? method : "OTHER",
    cf_ray: SAFE_RAY_ID.test(ray) ? ray : null,
  };
}

export function discordWebhookUrl(value: string | undefined): string {
  let url: URL;
  try {
    url = new URL(value?.trim() ?? "");
  } catch {
    throw new Error("DISCORD_SECURITY_WEBHOOK_URL is not a valid URL");
  }
  if (
    url.protocol !== "https:" ||
    (url.hostname !== "discord.com" && url.hostname !== "discordapp.com") ||
    url.port ||
    url.username ||
    url.password ||
    url.search ||
    url.hash ||
    !DISCORD_WEBHOOK_PATH.test(url.pathname)
  ) {
    throw new Error("DISCORD_SECURITY_WEBHOOK_URL must be an exact Discord webhook URL");
  }
  return url.href;
}

export function securityAlertRateLimitKey(
  event: Pick<SecurityAuditEvent, "kind" | "route">,
): string {
  const kind = {
    access_authentication_rejected: "access-auth",
    node_authentication_rejected: "node-auth",
    authorization_rejected: "authorization",
    cross_origin_mutation_rejected: "origin",
    sync_rate_limit_exceeded: "sync-limit",
    oversized_request_rejected: "oversize",
  }[event.kind];
  const route = {
    "/api/*": "api",
    "/sync/v1/nodes/:nodeId/exchange": "sync",
    "/": "root",
  }[event.route];
  return `${kind}:${route}`;
}

function discordPayload(event: SecurityAuditEvent): Record<string, unknown> {
  return {
    username: "INAS Cloud Hub Security",
    allowed_mentions: { parse: [] },
    embeds: [
      {
        title: "Cloud Hubでアクセスを拒否しました",
        color: event.status === 429 ? 0xf59e0b : 0xdc2626,
        timestamp: event.occurred_at,
        description:
          "認証情報・リクエスト本文・メールアドレス・IPアドレスは通知に含めていません。",
        fields: [
          { name: "事象", value: event.kind, inline: false },
          { name: "HTTP", value: `${event.status} ${event.method}`, inline: true },
          { name: "経路", value: event.route, inline: true },
          { name: "Cloudflare Ray ID", value: event.cf_ray ?? "なし", inline: false },
          { name: "監査イベントID", value: event.event_id, inline: false },
        ],
      },
    ],
  };
}
