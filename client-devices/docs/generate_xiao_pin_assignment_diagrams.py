#!/usr/bin/env python3
from __future__ import annotations

import base64
import html
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
TOP_IMAGE = ROOT / "xiao_esp32s3_top.png"
BACK_IMAGE = ROOT / "xiao_esp32s3_back.png"

BOARD_W = 7680
BOARD_H = 4320
BACK_Y = 4400
SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def moved(self, dx: int = 0, dy: int = 0) -> "Rect":
        return Rect(self.x + dx, self.y + dy, self.w, self.h)


@dataclass(frozen=True)
class Role:
    no: int
    title: str
    pins: str
    color: str
    rects: tuple[str, ...]


TOP_RECTS: dict[str, Rect] = {
    "BOOT": Rect(6268, 792, 540, 128),
    "GPIO0": Rect(5668, 792, 540, 128),
    "VBUS": Rect(4464, 1112, 540, 128),
    "GND_TOP": Rect(4464, 1268, 540, 128),
    "3V3": Rect(4464, 1424, 540, 128),
    "GPIO1": Rect(1480, 1112, 540, 128),
    "A0": Rect(2080, 1112, 540, 128),
    "D0": Rect(2680, 1112, 540, 128),
    "GPIO3": Rect(1480, 1424, 540, 128),
    "A2": Rect(2080, 1424, 540, 128),
    "D2": Rect(2680, 1424, 540, 128),
    "GPIO4": Rect(1480, 1584, 540, 128),
    "D3": Rect(2680, 1584, 540, 128),
    "GPIO5": Rect(1480, 1744, 540, 128),
    "D4": Rect(2680, 1744, 540, 128),
    "GPIO6": Rect(1480, 1904, 540, 128),
    "A5": Rect(2080, 1904, 540, 128),
    "D5": Rect(2680, 1904, 540, 128),
    "GPIO43": Rect(1480, 2064, 540, 128),
    "D6": Rect(2680, 2064, 540, 128),
    "GPIO7": Rect(5664, 1904, 540, 128),
    "D8": Rect(4464, 1904, 540, 128),
    "GPIO44": Rect(5664, 2064, 540, 128),
    "D7": Rect(4464, 2064, 540, 128),
}

BACK_RECTS: dict[str, Rect] = {
    "BAT_MINUS": Rect(4476, 1812, 540, 128).moved(dy=BACK_Y),
    "BAT_PLUS": Rect(4476, 1964, 540, 128).moved(dy=BACK_Y),
}

RECTS = TOP_RECTS | BACK_RECTS

ROLES: dict[str, tuple[Role, ...]] = {
    "wtr": (
        Role(1, "Soil moisture ADC", "A2 / D2 / GPIO3", "#16a34a", ("A2", "D2", "GPIO3")),
        Role(2, "Irrigation output", "D4 / GPIO5", "#2563eb", ("D4", "GPIO5")),
        Role(3, "Power input / GND", "VBUS / GND", "#0f766e", ("VBUS", "GND_TOP")),
        Role(4, "Setup AP", "BOOT / GPIO0", "#525252", ("BOOT", "GPIO0")),
    ),
    "env": (
        Role(1, "RS485 direction", "D4 / GPIO5", "#f59e0b", ("D4", "GPIO5")),
        Role(2, "RS485 TX", "D6 / GPIO43", "#7c3aed", ("D6", "GPIO43")),
        Role(3, "RS485 RX", "D7 / GPIO44", "#0891b2", ("D7", "GPIO44")),
        Role(4, "Power input / GND", "VBUS / GND", "#0f766e", ("VBUS", "GND_TOP")),
        Role(5, "Setup AP", "BOOT / GPIO0", "#525252", ("BOOT", "GPIO0")),
    ),
    "soi": (
        Role(1, "Soil moisture ADC", "A0 / D0 / GPIO1", "#16a34a", ("A0", "D0", "GPIO1")),
        Role(2, "Sensor power", "3.3V-OUT / GND", "#2563eb", ("3V3", "GND_TOP")),
        Role(3, "Battery", "BAT+ / BAT-", "#e11d48", ("BAT_PLUS", "BAT_MINUS")),
        Role(4, "Setup AP", "BOOT / GPIO0", "#525252", ("BOOT", "GPIO0")),
    ),
}

TITLES = {
    "wtr": "WTR single-channel watering device",
    "env": "ENV RS485 environmental sensor device",
    "soi": "SOI soil moisture sensor device",
}

OUTPUTS = {
    "wtr": ROOT / "xiao_esp32s3_pin_assignment_wtr.svg",
    "env": ROOT / "xiao_esp32s3_pin_assignment_env.svg",
    "soi": ROOT / "xiao_esp32s3_pin_assignment_soi.svg",
}


def data_uri(path: Path) -> str:
    mime = "image/png"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def svg_rect(rect: Rect, color: str) -> str:
    return (
        f'<rect x="{rect.x - 10}" y="{rect.y - 10}" width="{rect.w + 20}" '
        f'height="{rect.h + 20}" rx="24" fill="{color}" fill-opacity="0.16" '
        f'stroke="{color}" stroke-width="10"/>'
    )


def svg_badge(rect: Rect, role: Role) -> str:
    x = max(16, rect.x - 34)
    y = max(16, rect.y - 48)
    return (
        f'<g><rect x="{x}" y="{y}" width="92" height="72" rx="36" '
        f'fill="{role.color}" stroke="#ffffff" stroke-width="6"/>'
        f'<text x="{x + 46}" y="{y + 50}" text-anchor="middle" '
        f'font-family="Arial, sans-serif" font-size="48" font-weight="700" '
        f'fill="#ffffff">{role.no}</text></g>'
    )


def svg_legend(device: str, roles: tuple[Role, ...]) -> str:
    title = html.escape(TITLES[device])
    x, y, w, h = 220, 2600, 7240, 1120
    row_h = 150
    col_w = 3480
    parts = [
        f'<g font-family="Arial, sans-serif">',
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="24" '
        f'fill="#071015" fill-opacity="0.88" stroke="#d8dee9" stroke-opacity="0.55" '
        f'stroke-width="4"/>',
        f'<text x="{x + 80}" y="{y + 120}" font-size="92" font-weight="700" '
        f'fill="#ffffff">{title}</text>',
        f'<text x="{x + 80}" y="{y + 220}" font-size="52" fill="#cbd5e1">'
        f'Numbered highlights show the XIAO ESP32S3 pins used by this device.</text>',
    ]
    for idx, role in enumerate(roles):
        col = idx // 5
        row = idx % 5
        item_x = x + 80 + col * col_w
        item_y = y + 330 + row * row_h
        label = html.escape(f"{role.no}. {role.title}: {role.pins}")
        parts.append(
            f'<rect x="{item_x}" y="{item_y - 58}" width="78" height="78" rx="39" '
            f'fill="{role.color}" stroke="#ffffff" stroke-width="5"/>'
        )
        parts.append(
            f'<text x="{item_x + 39}" y="{item_y - 5}" text-anchor="middle" '
            f'font-size="52" font-weight="700" fill="#ffffff">{role.no}</text>'
        )
        parts.append(
            f'<text x="{item_x + 110}" y="{item_y - 4}" font-size="56" '
            f'fill="#ffffff">{label}</text>'
        )
    parts.append("</g>")
    return "\n".join(parts)


def build_svg(device: str, top_uri: str, back_uri: str) -> str:
    roles = ROLES[device]
    use_back = device == "soi"
    height = BACK_Y + BOARD_H if use_back else BOARD_H
    parts = [
        f'<svg xmlns="{SVG_NS}" width="{BOARD_W}" height="{height}" viewBox="0 0 {BOARD_W} {height}">',
        '<rect width="100%" height="100%" fill="#000000"/>',
        f'<image href="{top_uri}" x="0" y="0" width="{BOARD_W}" height="{BOARD_H}"/>',
    ]
    if use_back:
        parts.append(f'<image href="{back_uri}" x="0" y="{BACK_Y}" width="{BOARD_W}" height="{BOARD_H}"/>')
        parts.append(
            '<text x="220" y="4520" font-family="Arial, sans-serif" '
            'font-size="72" font-weight="700" fill="#ffffff">Back side: battery terminals</text>'
        )
    for role in roles:
        for rect_name in role.rects:
            parts.append(svg_rect(RECTS[rect_name], role.color))
        parts.append(svg_badge(RECTS[role.rects[0]], role))
    parts.append(svg_legend(device, roles))
    parts.append("</svg>")
    return "\n".join(parts)


def mx_style(style: str) -> str:
    return escape(style, {'"': "&quot;"})


def mx_value(value: str) -> str:
    return escape(value.replace("\n", "<br>"), {'"': "&quot;"})


def mx_cell(cell_id: str, value: str, style: str, rect: Rect, parent: str = "1") -> str:
    return (
        f'<mxCell id="{cell_id}" value="{mx_value(value)}" style="{mx_style(style)}" '
        f'vertex="1" parent="{parent}"><mxGeometry x="{rect.x}" y="{rect.y}" '
        f'width="{rect.w}" height="{rect.h}" as="geometry"/></mxCell>'
    )


def mx_image(cell_id: str, image_uri: str, rect: Rect) -> str:
    style = (
        "shape=image;imageAspect=1;aspect=fixed;verticalLabelPosition=bottom;"
        f"verticalAlign=top;image={image_uri};"
    )
    return mx_cell(cell_id, "", style, rect)


def mx_highlight(cell_id: str, rect: Rect, color: str) -> str:
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={color};fillOpacity=16;"
        f"strokeColor={color};strokeWidth=10;arcSize=14;"
    )
    return mx_cell(cell_id, "", style, Rect(rect.x - 10, rect.y - 10, rect.w + 20, rect.h + 20))


def mx_badge(cell_id: str, rect: Rect, role: Role) -> str:
    x = max(16, rect.x - 34)
    y = max(16, rect.y - 48)
    style = (
        f"ellipse;whiteSpace=wrap;html=1;fillColor={role.color};strokeColor=#ffffff;"
        "strokeWidth=6;fontColor=#ffffff;fontSize=48;fontStyle=1;align=center;verticalAlign=middle;"
    )
    return mx_cell(cell_id, str(role.no), style, Rect(x, y, 92, 72))


def mx_legend(device: str, roles: tuple[Role, ...]) -> list[str]:
    x, y, w, h = 220, 2600, 7240, 1120
    cells = [
        mx_cell(
            f"{device}_legend_bg",
            "",
            "rounded=1;whiteSpace=wrap;html=1;fillColor=#071015;fillOpacity=88;"
            "strokeColor=#d8dee9;strokeOpacity=55;strokeWidth=4;arcSize=8;",
            Rect(x, y, w, h),
        ),
        mx_cell(
            f"{device}_legend_title",
            TITLES[device],
            "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
            "fontColor=#ffffff;fontSize=92;fontStyle=1;",
            Rect(x + 80, y + 48, 4200, 120),
        ),
        mx_cell(
            f"{device}_legend_note",
            "Numbered highlights show the XIAO ESP32S3 pins used by this device.",
            "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
            "fontColor=#cbd5e1;fontSize=52;",
            Rect(x + 80, y + 156, 6200, 92),
        ),
    ]
    row_h = 150
    col_w = 3480
    for idx, role in enumerate(roles):
        col = idx // 5
        row = idx % 5
        item_x = x + 80 + col * col_w
        item_y = y + 330 + row * row_h
        cells.append(
            mx_cell(
                f"{device}_legend_badge_{role.no}",
                str(role.no),
                f"ellipse;whiteSpace=wrap;html=1;fillColor={role.color};strokeColor=#ffffff;"
                "strokeWidth=5;fontColor=#ffffff;fontSize=52;fontStyle=1;align=center;verticalAlign=middle;",
                Rect(item_x, item_y - 58, 78, 78),
            )
        )
        cells.append(
            mx_cell(
                f"{device}_legend_text_{role.no}",
                f"{role.no}. {role.title}: {role.pins}",
                "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
                "fontColor=#ffffff;fontSize=56;",
                Rect(item_x + 110, item_y - 74, 3100, 110),
            )
        )
    return cells


def build_mx_page(device: str, top_uri: str, back_uri: str) -> str:
    roles = ROLES[device]
    use_back = device == "soi"
    height = BACK_Y + BOARD_H if use_back else BOARD_H
    cells = [
        '<mxCell id="0"/>',
        '<mxCell id="1" parent="0"/>',
        mx_image(f"{device}_top_img", top_uri, Rect(0, 0, BOARD_W, BOARD_H)),
    ]
    if use_back:
        cells.append(mx_image(f"{device}_back_img", back_uri, Rect(0, BACK_Y, BOARD_W, BOARD_H)))
        cells.append(
            mx_cell(
                f"{device}_back_title",
                "Back side: battery terminals",
                "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
                "fontColor=#ffffff;fontSize=72;fontStyle=1;",
                Rect(220, 4448, 1600, 120),
            )
        )
    for role in roles:
        for index, rect_name in enumerate(role.rects):
            cells.append(mx_highlight(f"{device}_hl_{role.no}_{index}", RECTS[rect_name], role.color))
        cells.append(mx_badge(f"{device}_badge_{role.no}", RECTS[role.rects[0]], role))
    cells.extend(mx_legend(device, roles))
    root = "\n".join(cells)
    return (
        f'<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        f'pageWidth="{BOARD_W}" pageHeight="{height}" math="0" shadow="0">'
        f'<root>{root}</root></mxGraphModel>'
    )


def build_drawio(top_uri: str, back_uri: str) -> str:
    diagrams = []
    for device, name in (("wtr", "WTR"), ("env", "ENV"), ("soi", "SOI")):
        diagrams.append(
            f'<diagram id="pin_{device}" name="{name}">{build_mx_page(device, top_uri, back_uri)}</diagram>'
        )
    return (
        '<mxfile host="app.diagrams.net" modified="2026-07-12T00:00:00.000Z" '
        'agent="Codex" version="24.7.17" type="device">'
        + "\n".join(diagrams)
        + "</mxfile>\n"
    )


def main() -> None:
    top_uri = data_uri(TOP_IMAGE)
    back_uri = data_uri(BACK_IMAGE)
    for device, path in OUTPUTS.items():
        path.write_text(build_svg(device, top_uri, back_uri), encoding="utf-8")
    (ROOT / "xiao_esp32s3_pin_assignments.drawio").write_text(
        build_drawio(top_uri, back_uri),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
