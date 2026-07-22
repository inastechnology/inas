import { Hono } from "hono";

import type { AccessUser, AppServices, Env } from "../types";

type Variables = {
  services: AppServices;
  user: AccessUser;
};

const MAX_QUESTION_LENGTH = 500;

export function systemHelpRoutes() {
  const app = new Hono<{ Bindings: Env; Variables: Variables }>();

  app.post("/search", async (c) => {
    const body = await c.req.json().catch(() => null);
    const question = typeof body?.question === "string" ? body.question.trim() : "";
    if (!question) {
      return c.json({ error: "question is required" }, 400);
    }
    if (question.length > MAX_QUESTION_LENGTH) {
      return c.json({ error: `question must be ${MAX_QUESTION_LENGTH} characters or fewer` }, 400);
    }
    if (!c.env.SYSTEM_HELP_SEARCH) {
      return c.json({ error: "system help search is not configured" }, 503);
    }

    const result = await c.env.SYSTEM_HELP_SEARCH.search({
      query: question,
      ai_search_options: {
        retrieval: {
          retrieval_type: "hybrid",
          match_threshold: 0.2,
          max_num_results: 5,
          context_expansion: 1,
        },
      },
    });

    const sources = (result.chunks ?? []).map((chunk) => ({
      id: chunk.id,
      score: chunk.score,
      text: chunk.text,
      document: chunk.item?.key ?? "",
    }));
    return c.json({ question, search_query: result.search_query ?? question, sources });
  });

  return app;
}
