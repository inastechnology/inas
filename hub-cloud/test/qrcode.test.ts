import { BitMatrix, Decoder } from "@nuintun/qrcode";
import { describe, expect, it } from "vitest";

import { qrSvg, wifiQrPayload } from "../scripts/qrcode";

describe("factory QR artifacts", () => {
  it("encodes the local AP credential without adding a cloud credential", () => {
    const payload = wifiQrPayload("INAS-12;34", "pass:word");
    expect(payload).toBe("WIFI:T:WPA;S:INAS-12\\;34;P:pass\\:word;H:false;;");
    expect(decodeGeneratedSvg(qrSvg(payload))).toBe(payload);
    expect(payload).not.toContain("Bearer");
    expect(payload).not.toContain("turso");
  });

  it("encodes only the public customer URL in the Cloud Hub QR", () => {
    const url = "https://cloud-hub.inas-technologies.com/t/abc234def5/";
    expect(decodeGeneratedSvg(qrSvg(url))).toBe(url);
  });
});

function decodeGeneratedSvg(svg: string): string {
  const sizeMatch = svg.match(/viewBox="0 0 ([0-9]+) \1"/);
  const pathMatch = svg.match(/<path d="([^"]*)"/);
  if (!sizeMatch || !pathMatch) {
    throw new Error("generated QR SVG structure is invalid");
  }
  const quietZone = 4;
  const matrix = new BitMatrix(Number(sizeMatch[1]) - quietZone * 2);
  for (const match of pathMatch[1].matchAll(/M([0-9]+) ([0-9]+)h1v1h-1z/g)) {
    matrix.set(Number(match[1]) - quietZone, Number(match[2]) - quietZone);
  }
  return new Decoder().decode(matrix).content;
}
