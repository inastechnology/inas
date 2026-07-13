#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
DRAWIO = ROOT / "inas_system_diagrams.drawio"


@dataclass(frozen=True)
class Box:
    id: str
    x: int
    y: int
    w: int
    h: int
    label: str
    fill: str = "#ffffff"
    stroke: str = "#334155"


@dataclass(frozen=True)
class Arrow:
    source: str
    target: str
    label: str = ""
    stroke: str = "#475569"


@dataclass(frozen=True)
class Page:
    id: str
    name: str
    title: str
    svg_file: str
    boxes: tuple[Box, ...]
    arrows: tuple[Arrow, ...]
    notes: tuple[str, ...] = ()
    width: int = 1600
    height: int = 1000


PAGES: tuple[Page, ...] = (
    Page(
        id="system_architecture",
        name="System Architecture",
        title="INAS System Architecture",
        svg_file="inas_system_architecture.svg",
        boxes=(
            Box("admin", 80, 120, 220, 120, "Administrator\nBrowser / CLI", "#e0f2fe", "#0284c7"),
            Box("access", 390, 80, 230, 90, "Cloudflare Access\nAuth + allowed email", "#ede9fe", "#7c3aed"),
            Box("tunnel", 390, 210, 230, 90, "Cloudflare Tunnel\nlocal hub entry", "#f3e8ff", "#9333ea"),
            Box("worker", 390, 360, 230, 100, "Cloud app option\nWorkers + Hono\ninitial scope", "#faf5ff", "#a855f7"),
            Box("hub", 720, 140, 300, 230, "local hub\nFlask UI/API\nMQTT client\nOTA HTTP delivery\nscheduler / storage", "#dcfce7", "#16a34a"),
            Box("mqtt", 1130, 160, 220, 100, "MQTT broker\ncontrol/status topics", "#fef3c7", "#d97706"),
            Box("devices", 1080, 360, 320, 180, "Devices\nWTR: watering\nWRS: RS485 watering\nSOI: soil moisture\nENV: RS485 environment", "#fee2e2", "#dc2626"),
            Box("turso", 720, 520, 220, 110, "Turso / libSQL\nshared DB", "#e2e8f0", "#475569"),
            Box("storage", 980, 640, 220, 110, "Local / S3 storage\nimages, audio,\nartifacts", "#e2e8f0", "#475569"),
            Box("external", 1220, 650, 260, 110, "External data\nweather, research\nfuture image diagnosis", "#f8fafc", "#64748b"),
        ),
        arrows=(
            Arrow("admin", "access", "HTTPS admin entry", "#0284c7"),
            Arrow("access", "tunnel", "Tunnel option", "#7c3aed"),
            Arrow("tunnel", "hub", "http://localhost:39151", "#7c3aed"),
            Arrow("access", "worker", "Cloud app option", "#a855f7"),
            Arrow("worker", "turso", "management API read/write", "#a855f7"),
            Arrow("hub", "mqtt", "publish / subscribe", "#d97706"),
            Arrow("mqtt", "devices", "status / config / OTA offer", "#d97706"),
            Arrow("devices", "hub", "firmware.bin HTTP download", "#16a34a"),
            Arrow("hub", "turso", "state/event sync", "#475569"),
            Arrow("hub", "storage", "images/firmware/logs", "#475569"),
            Arrow("hub", "external", "weather/external fetch", "#64748b"),
        ),
        notes=(
            "Cloudflare Workers start as a Turso-backed management API/UI, not as a full local hub replacement.",
            "The Tunnel connector runs on the device side and exposes the local hub through Cloudflare Access.",
            "OTA firmware binaries are delivered by the hub HTTP endpoint, not over MQTT.",
        ),
    ),
    Page(
        id="data_control_flow",
        name="Data and Control Flow",
        title="Observation To Control Flow",
        svg_file="inas_data_control_flow.svg",
        boxes=(
            Box("wake", 70, 170, 190, 90, "1. Wake\nsample sensors", "#fee2e2", "#dc2626"),
            Box("status", 330, 160, 210, 110, "2. MQTT status\nmeasurements\nwake history", "#fef3c7", "#d97706"),
            Box("normalize", 610, 150, 230, 130, "3. Hub normalize\nsensor_measurements\nevents", "#dcfce7", "#16a34a"),
            Box("ui", 930, 110, 230, 110, "4. UI\ncharts, cards,\nhistory", "#e0f2fe", "#0284c7"),
            Box("field", 930, 290, 230, 130, "5. Field context\ncrop, cultivar,\ntarget ranges", "#f8fafc", "#64748b"),
            Box("candidate", 1220, 230, 250, 130, "6. Action candidates\nirrigation,\nfertilizer, misting\nonly irrigation now", "#ecfccb", "#65a30d"),
            Box("approval", 1220, 470, 250, 110, "7. Approval / log\naction_plans\nhuman evaluation", "#e0e7ff", "#4f46e5"),
            Box("command", 870, 550, 260, 120, "8. Device config\nor irrigation command\nMQTT publish", "#fef3c7", "#d97706"),
            Box("actuate", 520, 540, 230, 130, "9. Actuate\nWTR/WRS\nwatering control", "#fee2e2", "#dc2626"),
            Box("feedback", 180, 510, 230, 110, "10. Observe result\nevaluate on\nnext wake", "#dcfce7", "#16a34a"),
        ),
        arrows=(
            Arrow("wake", "status", "publish", "#d97706"),
            Arrow("status", "normalize", "subscribe", "#d97706"),
            Arrow("normalize", "ui", "time-series view", "#0284c7"),
            Arrow("field", "candidate", "target gap", "#65a30d"),
            Arrow("normalize", "candidate", "latest values", "#16a34a"),
            Arrow("candidate", "approval", "store/evaluate", "#4f46e5"),
            Arrow("approval", "command", "approved operation", "#4f46e5"),
            Arrow("command", "actuate", "MQTT control", "#d97706"),
            Arrow("actuate", "feedback", "irrigation result", "#dc2626"),
            Arrow("feedback", "wake", "improvement loop", "#16a34a"),
        ),
        notes=(
            "The grower UI should show irrigation time, soil moisture, wake state, and next action candidates before raw variable names.",
            "ENV/SOI/WTR/WRS payloads are normalized into vertical sensor_measurements records.",
        ),
    ),
    Page(
        id="device_placement_model",
        name="Device Placement Model",
        title="Field And Device Placement Model",
        svg_file="inas_device_placement_model.svg",
        boxes=(
            Box("field", 100, 120, 270, 140, "Field\ncrop, cultivar\ncultivation method\ntarget ranges", "#f8fafc", "#475569"),
            Box("section", 470, 100, 260, 110, "Section\ncrop or condition unit", "#e0f2fe", "#0284c7"),
            Box("ridge", 470, 270, 260, 110, "Ridge / bed\nsoil moisture and\nirrigation unit", "#dcfce7", "#16a34a"),
            Box("point", 470, 440, 260, 110, "Point\nspecific representative\nmeasurement", "#fef3c7", "#d97706"),
            Box("env", 870, 120, 240, 120, "ENV\nfield or section\ntemp, humidity, light\nEC/pH/NPK", "#ede9fe", "#7c3aed"),
            Box("soi", 870, 310, 240, 120, "SOI\nridge / point\nsoil moisture", "#fee2e2", "#dc2626"),
            Box("wtr", 870, 500, 240, 120, "WTR/WRS\nsection / ridge\nirrigation action", "#ecfccb", "#65a30d"),
            Box("cam", 1180, 160, 240, 110, "Camera\nfield / section\nimage observation", "#e2e8f0", "#475569"),
            Box("feedback", 1180, 390, 260, 150, "Growth feedback\nmeasurements + crop context\nwork log + images\nexternal data", "#f8fafc", "#64748b"),
        ),
        arrows=(
            Arrow("field", "section", "optional split", "#0284c7"),
            Arrow("section", "ridge", "split as needed", "#16a34a"),
            Arrow("ridge", "point", "measurement point", "#d97706"),
            Arrow("field", "env", "representative environment", "#7c3aed"),
            Arrow("ridge", "soi", "soil moisture", "#dc2626"),
            Arrow("ridge", "wtr", "irrigation target", "#65a30d"),
            Arrow("field", "cam", "image observation", "#475569"),
            Arrow("env", "feedback", "environment", "#7c3aed"),
            Arrow("soi", "feedback", "soil", "#dc2626"),
            Arrow("wtr", "feedback", "work result", "#65a30d"),
            Arrow("cam", "feedback", "image", "#475569"),
        ),
        notes=(
            "One ENV device can represent a small field. Split only when field, crop, sunlight, or drainage differences require it.",
            "device_placements decide which measurements affect which crop or field unit.",
        ),
    ),
    Page(
        id="ota_flow",
        name="OTA Flow",
        title="OTA Firmware Delivery",
        svg_file="inas_ota_flow.svg",
        boxes=(
            Box("build", 90, 160, 240, 110, "firmware build\nPlatformIO\nmanifest embedded", "#e0f2fe", "#0284c7"),
            Box("check", 410, 160, 240, 110, "format check\nINAS_FW_MANIFEST_V1\nsha256 / size", "#f8fafc", "#475569"),
            Box("upload", 730, 120, 260, 150, "Hub UI\nF/W registration\nupload / register API", "#dcfce7", "#16a34a"),
            Box("storage", 1080, 130, 320, 130, "firmware storage\nWORK_DIR/firmware/\n<kind>/<version>/firmware.bin", "#e2e8f0", "#475569"),
            Box("artifact", 730, 360, 260, 130, "artifact registration\nsize / sha256 / URL\nhttp://host:39151/firmware/...", "#ecfccb", "#65a30d"),
            Box("offer", 1080, 360, 300, 120, "MQTT OTA offer\ncontrol metadata only\nretained", "#fef3c7", "#d97706"),
            Box("download", 730, 610, 300, 120, "device HTTP download\nfirmware.bin\ncurrently http:// only", "#fee2e2", "#dc2626"),
            Box("status", 1080, 610, 300, 120, "MQTT OTA status\nreceived, verified,\napplied result", "#fef3c7", "#d97706"),
        ),
        arrows=(
            Arrow("build", "check", "make check-firmware", "#475569"),
            Arrow("check", "upload", "file select", "#16a34a"),
            Arrow("upload", "storage", "save binary", "#475569"),
            Arrow("upload", "artifact", "auto register", "#65a30d"),
            Arrow("artifact", "offer", "offer URL", "#d97706"),
            Arrow("offer", "download", "notify URL", "#d97706"),
            Arrow("storage", "download", "GET /firmware/...", "#dc2626"),
            Arrow("download", "status", "publish result", "#d97706"),
        ),
        notes=(
            "MQTT is only the control path. Firmware binaries are delivered by the Hub HTTP server.",
            "URLs are generated from FIRMWARE_BASE_URL / FIRMWARE_HOSTNAME / HOSTNAME, not a fixed hub.local name.",
            "Enable HTTPS only after device-side certificate validation is implemented.",
        ),
    ),
)


def center(box: Box) -> tuple[int, int]:
    return box.x + box.w // 2, box.y + box.h // 2


def edge_points(source: Box, target: Box) -> tuple[tuple[int, int], tuple[int, int]]:
    sx, sy = center(source)
    tx, ty = center(target)
    dx = tx - sx
    dy = ty - sy
    if abs(dx) / max(source.w, 1) > abs(dy) / max(source.h, 1):
        start = (source.x + (source.w if dx >= 0 else 0), sy)
    else:
        start = (sx, source.y + (source.h if dy >= 0 else 0))
    if abs(dx) / max(target.w, 1) > abs(dy) / max(target.h, 1):
        end = (target.x if dx >= 0 else target.x + target.w, ty)
    else:
        end = (tx, target.y if dy >= 0 else target.y + target.h)
    return start, end


def svg_text_lines(label: str, x: int, y: int, line_height: int, size: int, color: str = "#0f172a") -> str:
    lines = label.split("\n")
    start_y = y - (len(lines) - 1) * line_height // 2
    tspans = []
    for i, line in enumerate(lines):
        tspans.append(
            f'<tspan x="{x}" y="{start_y + i * line_height}">{escape(line)}</tspan>'
        )
    return (
        f'<text text-anchor="middle" font-family="Arial, sans-serif" font-size="{size}" '
        f'font-weight="700" fill="{color}">' + "".join(tspans) + "</text>"
    )


def build_svg(page: Page) -> str:
    boxes = {box.id: box for box in page.boxes}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.width}" height="{page.height}" '
        f'viewBox="0 0 {page.width} {page.height}">',
        '<defs><marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" '
        'orient="auto" markerUnits="strokeWidth"><path d="M2,2 L10,6 L2,10 Z" fill="#475569"/></marker></defs>',
        '<rect width="100%" height="100%" fill="#f8fafc"/>',
        f'<text x="60" y="62" font-family="Arial, sans-serif" font-size="36" '
        f'font-weight="700" fill="#0f172a">{escape(page.title)}</text>',
    ]
    for arrow in page.arrows:
        source = boxes[arrow.source]
        target = boxes[arrow.target]
        (x1, y1), (x2, y2) = edge_points(source, target)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{arrow.stroke}" '
            f'stroke-width="3" marker-end="url(#arrow)"/>'
        )
        if arrow.label:
            mx = (x1 + x2) // 2
            my = (y1 + y2) // 2 - 8
            parts.append(
                f'<rect x="{mx - 90}" y="{my - 22}" width="180" height="34" rx="8" '
                f'fill="#f8fafc" fill-opacity="0.92"/>'
            )
            parts.append(
                f'<text x="{mx}" y="{my}" text-anchor="middle" font-family="Arial, sans-serif" '
                f'font-size="16" font-weight="700" fill="{arrow.stroke}">{escape(arrow.label)}</text>'
            )
    for box in page.boxes:
        parts.append(
            f'<rect x="{box.x}" y="{box.y}" width="{box.w}" height="{box.h}" rx="12" '
            f'fill="{box.fill}" stroke="{box.stroke}" stroke-width="3"/>'
        )
        parts.append(svg_text_lines(box.label, box.x + box.w // 2, box.y + box.h // 2 + 8, 26, 20))
    if page.notes:
        note_x, note_y = 70, page.height - 130
        parts.append(
            f'<rect x="{note_x}" y="{note_y}" width="{page.width - 140}" height="88" '
            f'rx="12" fill="#ffffff" stroke="#cbd5e1" stroke-width="2"/>'
        )
        for i, note in enumerate(page.notes[:3]):
            parts.append(
                f'<text x="{note_x + 26}" y="{note_y + 30 + i * 24}" '
                f'font-family="Arial, sans-serif" font-size="17" fill="#334155">- {escape(note)}</text>'
            )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def mx_value(value: str) -> str:
    return escape(value.replace("\n", "<br>"), {'"': "&quot;"})


def mx_style(style: str) -> str:
    return escape(style, {'"': "&quot;"})


def mx_box(box: Box) -> str:
    style = (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={box.fill};strokeColor={box.stroke};"
        "strokeWidth=3;arcSize=8;fontColor=#0f172a;fontSize=20;fontStyle=1;"
        "align=center;verticalAlign=middle;"
    )
    return (
        f'<mxCell id="{box.id}" value="{mx_value(box.label)}" style="{mx_style(style)}" '
        f'vertex="1" parent="1"><mxGeometry x="{box.x}" y="{box.y}" width="{box.w}" '
        f'height="{box.h}" as="geometry"/></mxCell>'
    )


def mx_arrow(index: int, arrow: Arrow) -> str:
    style = (
        f"endArrow=block;html=1;rounded=0;strokeColor={arrow.stroke};strokeWidth=3;"
        "fontColor=#334155;fontSize=16;fontStyle=1;edgeStyle=orthogonalEdgeStyle;"
    )
    return (
        f'<mxCell id="edge_{index}" value="{mx_value(arrow.label)}" style="{mx_style(style)}" '
        f'edge="1" parent="1" source="{arrow.source}" target="{arrow.target}">'
        '<mxGeometry relative="1" as="geometry"/></mxCell>'
    )


def mx_note(page: Page) -> list[str]:
    if not page.notes:
        return []
    x, y, w, h = 70, page.height - 130, page.width - 140, 88
    note = "\n".join(f"- {line}" for line in page.notes[:3])
    return [
        (
            f'<mxCell id="{page.id}_note" value="{mx_value(note)}" '
            'style="rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=#cbd5e1;'
            'strokeWidth=2;fontColor=#334155;fontSize=17;align=left;verticalAlign=middle;spacingLeft=16;" '
            f'vertex="1" parent="1"><mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" '
            'as="geometry"/></mxCell>'
        )
    ]


def build_mx_page(page: Page) -> str:
    cells = [
        '<mxCell id="0"/>',
        '<mxCell id="1" parent="0"/>',
        (
            f'<mxCell id="{page.id}_title" value="{mx_value(page.title)}" '
            'style="text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;'
            'fontColor=#0f172a;fontSize=36;fontStyle=1;" vertex="1" parent="1">'
            '<mxGeometry x="60" y="24" width="700" height="60" as="geometry"/></mxCell>'
        ),
    ]
    cells.extend(mx_box(box) for box in page.boxes)
    cells.extend(mx_arrow(index, arrow) for index, arrow in enumerate(page.arrows, 1))
    cells.extend(mx_note(page))
    return (
        f'<mxGraphModel dx="1600" dy="900" grid="1" gridSize="10" guides="1" tooltips="1" '
        f'connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page.width}" '
        f'pageHeight="{page.height}" math="0" shadow="0"><root>'
        + "\n".join(cells)
        + "</root></mxGraphModel>"
    )


def build_drawio() -> str:
    diagrams = []
    for page in PAGES:
        diagrams.append(
            f'<diagram id="{page.id}" name="{escape(page.name)}">{build_mx_page(page)}</diagram>'
        )
    return (
        '<mxfile host="app.diagrams.net" modified="2026-07-12T00:00:00.000Z" '
        'agent="Codex" version="24.7.17" type="device">'
        + "\n".join(diagrams)
        + "</mxfile>\n"
    )


def main() -> None:
    for page in PAGES:
        (ROOT / page.svg_file).write_text(build_svg(page), encoding="utf-8")
    DRAWIO.write_text(build_drawio(), encoding="utf-8")


if __name__ == "__main__":
    main()
