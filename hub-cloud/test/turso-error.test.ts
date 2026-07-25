import { describe, expect, it } from "vitest";

import { isTursoHttpError } from "../scripts/turso-error";

describe("Turso API errors", () => {
  it("recognizes the SDK's unexported runtime error shape", () => {
    const error = Object.assign(new Error("database not found"), {
      name: "TursoClientError",
      status: 404,
    });

    expect(isTursoHttpError(error, 404)).toBe(true);
    expect(isTursoHttpError(error, 401)).toBe(false);
  });

  it("does not accept arbitrary status-bearing values", () => {
    expect(isTursoHttpError({ name: "TursoClientError", status: 404 }, 404)).toBe(false);
    expect(isTursoHttpError(Object.assign(new Error("missing"), { status: 404 }), 404)).toBe(false);
  });
});
