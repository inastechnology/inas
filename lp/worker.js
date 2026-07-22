const API_PATH = "/app/api/leads";
const HEALTH_PATH = "/app/api/health";
const ALLOWED_ROLES = new Set(["home", "farmer", "company", "school", "research", "other"]);
const ALLOWED_SCALES = new Set(["pots", "under_100m2", "100_1000m2", "over_1000m2", "planning"]);
const ALLOWED_PAINS = new Set(["remote_monitoring", "task_planning", "watering", "records"]);
const ATTRIBUTION_KEYS = new Set(["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "gclid", "fbclid", "landing_path", "referrer_host"]);
const MAX_BODY_BYTES = 16_384;

const securityHeaders = {
  "Content-Security-Policy": "default-src 'self'; base-uri 'self'; connect-src 'self' https://challenges.cloudflare.com https://www.google-analytics.com https://region1.google-analytics.com; font-src 'self'; frame-ancestors 'none'; frame-src https://challenges.cloudflare.com; img-src 'self' data:; media-src 'self'; object-src 'none'; script-src 'self' https://challenges.cloudflare.com https://www.googletagmanager.com; style-src 'self'; form-action 'self'",
  "Permissions-Policy": "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
};

function json(payload, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "application/json; charset=utf-8",
      ...securityHeaders,
      ...extraHeaders,
    },
  });
}

function text(value, status = 200, extraHeaders = {}) {
  return new Response(value, {
    status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": "text/plain; charset=utf-8",
      ...securityHeaders,
      ...extraHeaders,
    },
  });
}

function isAllowedOrigin(request, url) {
  const origin = request.headers.get("Origin");
  if (!origin) return false;
  if (origin === "https://inas-technologies.com") return true;
  if (url.protocol === "http:" && origin === url.origin) return true;
  try {
    const originUrl = new URL(origin);
    return originUrl.protocol === "http:" && (originUrl.hostname === "127.0.0.1" || originUrl.hostname === "localhost");
  } catch {
    return false;
  }
}

function cleanString(value, maxLength) {
  return typeof value === "string" ? value.trim().slice(0, maxLength) : "";
}

function cleanAttribution(value) {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result = {};
  for (const [key, rawValue] of Object.entries(value)) {
    if (!ATTRIBUTION_KEYS.has(key) || typeof rawValue !== "string") continue;
    const limit = key === "landing_path" ? 1000 : 300;
    const cleaned = rawValue.trim().slice(0, limit);
    if (cleaned) result[key] = cleaned;
  }
  return result;
}

function validatePayload(raw) {
  const role = cleanString(raw?.role, 30);
  const scale = cleanString(raw?.scale, 30);
  const pain = cleanString(raw?.pain, 40);
  const email = cleanString(raw?.email, 254);
  const message = cleanString(raw?.message, 1000);
  const website = cleanString(raw?.website, 200);
  const turnstileToken = cleanString(raw?.turnstile_token, 2048);
  const audience = cleanString(raw?.audience, 30);
  const source = cleanString(raw?.source, 80);
  const emailLooksValid = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

  if (!ALLOWED_ROLES.has(role)) return { error: "invalid_role" };
  if (!ALLOWED_SCALES.has(scale)) return { error: "invalid_scale" };
  if (!ALLOWED_PAINS.has(pain)) return { error: "invalid_pain" };
  if (!emailLooksValid) return { error: "invalid_email" };
  if (raw?.consent !== true) return { error: "consent_required" };
  if (source !== "inas-demand-validation-lp") return { error: "invalid_source" };

  return {
    value: {
      role,
      scale,
      pain,
      email,
      normalizedEmail: email.toLowerCase(),
      message,
      website,
      turnstileToken,
      audience: ["home", "farmer", "team"].includes(audience) ? audience : "home",
      source,
      attribution: cleanAttribution(raw.attribution),
    },
  };
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

async function isWithinRateLimit(request, env, normalizedEmail) {
  if (!env.LEAD_RATE_LIMITER?.limit) return true;
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const emailKey = await sha256(normalizedEmail);
  const [actorResult, emailResult] = await Promise.all([
    env.LEAD_RATE_LIMITER.limit({ key: `lead-ip:${ip}` }),
    env.LEAD_RATE_LIMITER.limit({ key: `lead-email:${emailKey}` }),
  ]);
  return actorResult.success && emailResult.success;
}

async function validateTurnstile(request, env, token) {
  if (!env.TURNSTILE_SECRET_KEY) return { success: true, skipped: true };
  if (!token) return { success: false };

  const body = new FormData();
  body.set("secret", env.TURNSTILE_SECRET_KEY);
  body.set("response", token);
  body.set("idempotency_key", crypto.randomUUID());
  const remoteIp = request.headers.get("CF-Connecting-IP");
  if (remoteIp) body.set("remoteip", remoteIp);

  try {
    const response = await fetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
      method: "POST",
      body,
    });
    if (!response.ok) return { success: false };
    const result = await response.json();
    const expectedHostname = env.TURNSTILE_EXPECTED_HOSTNAME || "inas-technologies.com";
    return {
      success: result.success === true && result.hostname === expectedHostname && result.action === "lead_submit",
    };
  } catch {
    return { success: false };
  }
}

async function handleLead(request, env, ctx, url) {
  if (request.method !== "POST") {
    return json({ ok: false, error: "method_not_allowed" }, 405, { Allow: "POST" });
  }
  if (!isAllowedOrigin(request, url)) return json({ ok: false, error: "forbidden_origin" }, 403);
  const contentType = request.headers.get("Content-Type") || "";
  if (!contentType.toLowerCase().startsWith("application/json")) {
    return json({ ok: false, error: "unsupported_media_type" }, 415);
  }
  const announcedLength = Number(request.headers.get("Content-Length") || 0);
  if (announcedLength > MAX_BODY_BYTES) return json({ ok: false, error: "payload_too_large" }, 413);

  let raw;
  try {
    const body = await request.text();
    if (new TextEncoder().encode(body).byteLength > MAX_BODY_BYTES) {
      return json({ ok: false, error: "payload_too_large" }, 413);
    }
    raw = JSON.parse(body);
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  const validated = validatePayload(raw);
  if (validated.error) return json({ ok: false, error: validated.error }, 400);
  const lead = validated.value;

  // Silently accept automated submissions that fill the hidden field, without storing personal data.
  if (lead.website) return json({ ok: true }, 202);

  if (!(await isWithinRateLimit(request, env, lead.normalizedEmail))) {
    return json({ ok: false, error: "rate_limited" }, 429, { "Retry-After": "60" });
  }

  const turnstile = await validateTurnstile(request, env, lead.turnstileToken);
  if (!turnstile.success) return json({ ok: false, error: "turnstile_failed" }, 400);
  if (!env.LEADS_DB?.prepare) return json({ ok: false, error: "service_unavailable" }, 503);

  const submissionId = crypto.randomUUID();
  const createdAt = new Date().toISOString();
  try {
    await env.LEADS_DB.prepare(
      `INSERT INTO leads (
        submission_id, role, scale, pain, email, message, audience,
        attribution_json, source, created_at, status
      ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, 'new')`,
    ).bind(
      submissionId,
      lead.role,
      lead.scale,
      lead.pain,
      lead.email,
      lead.message,
      lead.audience,
      JSON.stringify(lead.attribution),
      lead.source,
      createdAt,
    ).run();
  } catch (error) {
    console.error("lead_insert_failed", error instanceof Error ? error.message : "unknown");
    return json({ ok: false, error: "storage_error" }, 500);
  }

  const retentionDays = Math.max(1, Math.min(730, Number(env.LEAD_RETENTION_DAYS || 365)));
  if (ctx?.waitUntil) {
    ctx.waitUntil(
      env.LEADS_DB.prepare("DELETE FROM leads WHERE created_at < datetime('now', ?1)")
        .bind(`-${retentionDays} days`)
        .run()
        .catch(() => undefined),
    );
  }

  return json({ ok: true, submission_id: submissionId }, 201);
}

async function withAssetHeaders(request, response) {
  const headers = new Headers(response.headers);
  for (const [key, value] of Object.entries(securityHeaders)) headers.set(key, value);
  const url = new URL(request.url);
  const contentType = headers.get("Content-Type") || "";
  if (url.pathname.endsWith("/config.js") || contentType.includes("text/html")) {
    headers.set("Cache-Control", "no-cache, no-store, must-revalidate");
  }
  return new Response(response.body, { status: response.status, statusText: response.statusText, headers });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/app") {
      url.pathname = "/app/";
      return new Response(null, {
        status: 308,
        headers: {
          Location: url.toString(),
          ...securityHeaders,
        },
      });
    }
    if (url.pathname === HEALTH_PATH) return text("ok\n");
    if (url.pathname === API_PATH) return handleLead(request, env, ctx, url);
    return withAssetHeaders(request, await env.ASSETS.fetch(request));
  },
};

export { handleLead, validatePayload };
