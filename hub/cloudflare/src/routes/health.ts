import { Hono } from "hono";

import type { AccessUser, AppServices, Env } from "../types";

type Variables = {
  services: AppServices;
  user: AccessUser;
};

export function healthRoutes() {
  const app = new Hono<{ Bindings: Env; Variables: Variables }>();

  app.get("/", (c) =>
    c.json({
      ok: true,
      service: "ina-device-hub-cloud",
      tursoConfigured: Boolean(c.env.TURSO_DATABASE_URL && c.env.TURSO_AUTH_TOKEN),
      accessConfigured: Boolean(c.env.CLOUDFLARE_ACCESS_TEAM_DOMAIN && c.env.CLOUDFLARE_ACCESS_POLICY_AUD),
    }),
  );

  return app;
}
