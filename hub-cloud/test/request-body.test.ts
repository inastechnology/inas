import { describe, expect, it } from "vitest";

import { readSyncJson } from "../src/request-body";

describe("bounded Sync body reader", () => {
  it("accepts gzip JSON while bounding decompressed bytes", async () => {
    const body = JSON.stringify({ protocol_version: "1.0", value: "ok" });
    const compressed = await new Response(
      new Blob([body]).stream().pipeThrough(new CompressionStream("gzip")),
    ).arrayBuffer();
    const request = new Request("https://hub.example/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Content-Length": String(compressed.byteLength),
      },
      body: compressed,
    });
    await expect(readSyncJson(request)).resolves.toEqual({ protocol_version: "1.0", value: "ok" });
  });

  it("rejects a compressed expansion beyond 1 MiB", async () => {
    const body = JSON.stringify({ value: "a".repeat(1024 * 1024) });
    const compressed = await new Response(
      new Blob([body]).stream().pipeThrough(new CompressionStream("gzip")),
    ).arrayBuffer();
    const request = new Request("https://hub.example/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
        "Content-Length": String(compressed.byteLength),
      },
      body: compressed,
    });
    await expect(readSyncJson(request)).rejects.toMatchObject({ status: 413 });
  });

  it("bounds encoded bytes even when Content-Length is absent", async () => {
    const request = new Request("https://hub.example/sync", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Encoding": "gzip",
      },
      body: new Uint8Array(1024 * 1024 + 1),
    });
    await expect(readSyncJson(request)).rejects.toMatchObject({ status: 413 });
  });
});
