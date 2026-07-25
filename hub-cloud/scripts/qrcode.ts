import { Byte, Encoder } from "@nuintun/qrcode";

export function wifiQrPayload(ssid: string, password: string): string {
  return `WIFI:T:WPA;S:${wifiQrEscape(ssid)};P:${wifiQrEscape(password)};H:false;;`;
}

export function qrSvg(value: string): string {
  const encoded = new Encoder({ level: "M" }).encode(new Byte(value));
  const quietZone = 4;
  const viewBoxSize = encoded.size + quietZone * 2;
  const modules: string[] = [];
  for (let y = 0; y < encoded.size; y += 1) {
    for (let x = 0; x < encoded.size; x += 1) {
      if (encoded.get(x, y)) {
        modules.push(`M${x + quietZone} ${y + quietZone}h1v1h-1z`);
      }
    }
  }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${viewBoxSize} ${viewBoxSize}" ` +
    `shape-rendering="crispEdges" role="img" aria-label="QR code">` +
    `<rect width="100%" height="100%" fill="#fff"/>` +
    `<path d="${modules.join("")}" fill="#000"/></svg>\n`
  );
}

function wifiQrEscape(value: string): string {
  return value.replace(/([\\;,:"'])/g, "\\$1");
}
