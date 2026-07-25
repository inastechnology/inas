import { describe, expect, it } from "vitest";

import { canonicalJson } from "../src/database";
import { assertSafeJson } from "../src/json-safety";

describe("untrusted JSON safety", () => {
  it("preserves canonical object keys without prototype mutation", () => {
    const value = JSON.parse('{"safe":1,"nested":{"value":2}}');
    assertSafeJson(value, "payload");
    expect(canonicalJson(value)).toBe('{"nested":{"value":2},"safe":1}');
  });

  it("rejects prototype keys and excessive nesting", () => {
    const polluted = JSON.parse('{"__proto__":{"admin":true}}');
    expect(() => assertSafeJson(polluted, "payload")).toThrow("unsafe object key");

    let nested: Record<string, unknown> = {};
    const root = nested;
    for (let index = 0; index < 25; index += 1) {
      nested.value = {};
      nested = nested.value as Record<string, unknown>;
    }
    expect(() => assertSafeJson(root, "payload")).toThrow("nested too deeply");
  });
});
