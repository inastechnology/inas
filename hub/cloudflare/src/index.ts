import { Hono } from "hono";

import { accessAuth, type VerifyAccessJwt } from "./access";
import { createServices } from "./repositories";
import { eventsRoutes } from "./routes/events";
import { healthRoutes } from "./routes/health";
import { systemHelpRoutes } from "./routes/system-help";
import type { AccessUser, AppServices, Env } from "./types";

type Variables = {
  services: AppServices;
  user: AccessUser;
};

export function createApp(options: { servicesFactory?: (env: Env) => AppServices; verifyAccessJwt?: VerifyAccessJwt } = {}) {
  const servicesFactory = options.servicesFactory ?? createServices;
  const app = new Hono<{ Bindings: Env; Variables: Variables }>();

  app.get("/", (c) => c.redirect("/api/health"));
  app.route("/api/health", healthRoutes());

  app.use(
    "/api/*",
    accessAuth({
      services: (c) => {
        const services = servicesFactory(c.env);
        c.set("services", services);
        return services;
      },
      verify: options.verifyAccessJwt,
    }),
  );
  app.get("/api/me", (c) => c.json({ user: c.get("user") }));
  app.route("/api/events", eventsRoutes());
  app.route("/api/system-help", systemHelpRoutes());

  app.notFound((c) => c.json({ error: "not found" }, 404));

  app.onError((error, c) => {
    console.error(error);
    return c.json({ error: "internal server error" }, 500);
  });

  return app;
}

export default {
  fetch(request: Request, env: Env, ctx: ExecutionContext) {
    return createApp().fetch(request, env, ctx);
  },
};
