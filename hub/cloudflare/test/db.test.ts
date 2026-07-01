import { describe, expect, it } from "vitest";

import { jsonPayload, parseJsonPayload } from "../src/db";

describe("db payload helpers", () => {
  it("serializes undefined and null as SQL null", () => {
    expect(jsonPayload(undefined)).toBeNull();
    expect(jsonPayload(null)).toBeNull();
  });

  it("round-trips JSON payload strings", () => {
    const encoded = jsonPayload({ battery_v: 3.7 });

    expect(encoded).toBe('{"battery_v":3.7}');
    expect(parseJsonPayload(encoded)).toEqual({ battery_v: 3.7 });
  });

  it("keeps non-JSON payload strings readable", () => {
    expect(parseJsonPayload("raw text")).toBe("raw text");
  });
});
