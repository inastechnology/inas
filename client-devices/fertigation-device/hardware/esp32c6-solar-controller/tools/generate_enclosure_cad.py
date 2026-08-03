#!/usr/bin/env python3
"""Generate Rev A enclosure mounting and connector-cutout DXF/SVG drawings."""

from __future__ import annotations

import csv
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CAD_DIR = ROOT / "enclosure"
EXPORT_DIR = ROOT / "exports" / "mechanical"


class Dxf:
    def __init__(self) -> None:
        self.entities: list[str] = []

    def pair(self, code: int, value) -> None:
        self.entities.extend((str(code), str(value)))

    def line(self, x1: float, y1: float, x2: float, y2: float, layer: str) -> None:
        self.pair(0, "LINE")
        self.pair(8, layer)
        self.pair(10, f"{x1:.4f}")
        self.pair(20, f"{y1:.4f}")
        self.pair(11, f"{x2:.4f}")
        self.pair(21, f"{y2:.4f}")

    def circle(self, x: float, y: float, radius: float, layer: str) -> None:
        self.pair(0, "CIRCLE")
        self.pair(8, layer)
        self.pair(10, f"{x:.4f}")
        self.pair(20, f"{y:.4f}")
        self.pair(40, f"{radius:.4f}")

    def polyline(
        self, points: list[tuple[float, float]], layer: str, *, closed: bool = True
    ) -> None:
        self.pair(0, "LWPOLYLINE")
        self.pair(8, layer)
        self.pair(90, len(points))
        self.pair(70, 1 if closed else 0)
        for x, y in points:
            self.pair(10, f"{x:.4f}")
            self.pair(20, f"{y:.4f}")

    def text(self, x: float, y: float, value: str, layer: str, height: float = 3) -> None:
        self.pair(0, "TEXT")
        self.pair(8, layer)
        self.pair(10, f"{x:.4f}")
        self.pair(20, f"{y:.4f}")
        self.pair(40, f"{height:.4f}")
        self.pair(1, value)

    def write(self, path: Path) -> None:
        header = [
            "0",
            "SECTION",
            "2",
            "HEADER",
            "9",
            "$INSUNITS",
            "70",
            "4",
            "0",
            "ENDSEC",
            "0",
            "SECTION",
            "2",
            "ENTITIES",
        ]
        footer = ["0", "ENDSEC", "0", "EOF"]
        path.write_text("\n".join(header + self.entities + footer) + "\n", encoding="ascii")


def rect(dxf: Dxf, x: float, y: float, width: float, height: float, layer: str) -> None:
    dxf.polyline(
        [(x, y), (x + width, y), (x + width, y + height), (x, y + height)],
        layer,
    )


def x_lok_d_cut(
    centre_x: float, centre_y: float, *, diameter: float = 20.8
) -> list[tuple[float, float]]:
    """Return the official Ø20.8 / 19.4 mm D-cut profile as a polygon."""

    radius = diameter / 2
    flat_x = centre_x - 9.0  # 19.4 mm from the opposite circular extreme.
    intersection_y = math.sqrt(radius**2 - (flat_x - centre_x) ** 2)
    points = [(flat_x, centre_y - intersection_y)]
    start = math.atan2(-intersection_y, flat_x - centre_x)
    end = 2 * math.pi - start
    for index in range(49):
        angle = start + (end - start) * index / 48
        points.append(
            (
                centre_x + radius * math.cos(angle),
                centre_y + radius * math.sin(angle),
            )
        )
    points.append((flat_x, centre_y + intersection_y))
    return points


def generate_mounting_plate() -> None:
    # Takachi BMP3040Z official plate: 265 x 365 mm, existing M5 pitch
    # 228 x 325 mm.  The controller PCB is 180 x 115 mm.
    plate_w, plate_h = 265.0, 365.0
    pcb_x, pcb_y = 42.5, 30.0
    pcb_w, pcb_h = 180.0, 115.0
    pcb_holes = [
        (pcb_x + 4.0, pcb_y + 4.0),
        (pcb_x + 176.0, pcb_y + 4.0),
        (pcb_x + 4.0, pcb_y + 111.0),
        (pcb_x + 176.0, pcb_y + 111.0),
    ]
    existing_holes = [
        ((plate_w - 228.0) / 2, (plate_h - 325.0) / 2),
        ((plate_w + 228.0) / 2, (plate_h - 325.0) / 2),
        ((plate_w - 228.0) / 2, (plate_h + 325.0) / 2),
        ((plate_w + 228.0) / 2, (plate_h + 325.0) / 2),
    ]

    dxf = Dxf()
    rect(dxf, 0, 0, plate_w, plate_h, "PLATE_OUTLINE")
    rect(dxf, pcb_x, pcb_y, pcb_w, pcb_h, "PCB_OUTLINE")
    for x, y in existing_holes:
        dxf.circle(x, y, 2.75, "EXISTING_M5")
    for x, y in pcb_holes:
        dxf.circle(x, y, 1.75, "PCB_M3_DRILL")

    # The pictured controller dimensions are reference measurements, not a
    # manufacturer drawing.  Keep these on a non-release layer.
    charger_x, charger_y = 65.5, 240.0
    rect(dxf, charger_x, charger_y, 134.0, 70.0, "MPPT_VERIFY")
    for x in (charger_x + 4.0, charger_x + 130.0):
        for y in (charger_y + 10.0, charger_y + 60.0):
            dxf.circle(x, y, 2.25, "MPPT_VERIFY")
    dxf.text(22.5, 177.0, "70 mm MIN HARNESS / FUSE SERVICE ZONE", "NOTES")
    dxf.text(
        65.5,
        315.0,
        "MPPT 134x70 / 126x50 HOLES - VERIFY PHYSICAL UNIT",
        "NOTES",
    )
    dxf.text(42.5, 20.0, "PCB 180x115; 4x M3.5 DRILL", "NOTES")
    dxf.write(CAD_DIR / "bmp3040z-mounting-plate-rev-a.dxf")

    scale = 2
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{plate_w*scale}" height="{plate_h*scale}" viewBox="0 0 {plate_w} {plate_h}">',
        '<rect width="100%" height="100%" fill="#f7f7f2"/>',
        f'<rect x="0.5" y="0.5" width="{plate_w-1}" height="{plate_h-1}" fill="none" stroke="#222" stroke-width="1"/>',
        f'<rect x="{pcb_x}" y="{plate_h-pcb_y-pcb_h}" width="{pcb_w}" height="{pcb_h}" fill="#2f6f4e" fill-opacity=".18" stroke="#2f6f4e"/>',
        f'<rect x="{charger_x}" y="{plate_h-charger_y-70}" width="134" height="70" fill="#277da1" fill-opacity=".15" stroke="#277da1" stroke-dasharray="4 2"/>',
    ]
    for x, y in existing_holes:
        svg.append(
            f'<circle cx="{x}" cy="{plate_h-y}" r="2.75" fill="none" stroke="#555"/>'
        )
    for x, y in pcb_holes:
        svg.append(
            f'<circle cx="{x}" cy="{plate_h-y}" r="1.75" fill="#d62828"/>'
        )
    svg.extend(
        [
            f'<text x="{pcb_x+5}" y="{plate_h-pcb_y-pcb_h+10}" font-size="5">CONTROLLER PCB 180 x 115</text>',
            f'<text x="{charger_x+4}" y="{plate_h-charger_y-70+10}" font-size="5">MPPT REFERENCE - VERIFY</text>',
            "</svg>",
        ]
    )
    (EXPORT_DIR / "bmp3040z-mounting-plate-rev-a.svg").write_text(
        "\n".join(svg) + "\n", encoding="utf-8"
    )


def generate_panel_cutouts() -> None:
    dxf = Dxf()
    rect(dxf, 0, 0, 265, 100, "PANEL_REFERENCE")
    for index, x in enumerate((45.0, 88.0, 131.0, 174.0, 217.0), start=1):
        dxf.polyline(x_lok_d_cut(x, 50.0), "XLOK_CUT")
        dxf.text(x - 8, 70, f"OUT{index}", "LABEL", 3)
    dxf.text(8, 8, "5x AMPHENOL X-LOK CC: D-CUT 20.8 / 19.4", "NOTES")
    dxf.text(8, 14, "REFERENCE FLAT PANEL ONLY - CONFIRM BCPR WALL CLEARANCE", "NOTES")
    dxf.write(CAD_DIR / "output-panel-cutouts-rev-a.dxf")

    coupon = Dxf()
    coupon.polyline(x_lok_d_cut(20, 20), "XLOK_CUT")
    coupon.circle(55, 20, 8.1, "M16_CUT")
    coupon.text(8, 37, "X-LOK CC-03: 20.8 / 19.4 D-CUT", "NOTES", 2.5)
    coupon.text(43, 37, "M12 REAR M16: DIA 16.2", "NOTES", 2.5)
    coupon.write(CAD_DIR / "connector-cutout-coupons-rev-a.dxf")

    with (CAD_DIR / "mechanical-dimensions.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as output:
        writer = csv.writer(output)
        writer.writerow(["Item", "Dimension", "Value mm", "Release status"])
        writer.writerows(
            [
                ["Controller PCB", "Outline", "180 x 115", "RELEASED"],
                ["Controller PCB", "Mount hole", "4 x 3.2", "RELEASED"],
                ["Controller PCB", "Hole pitch", "172 x 107", "RELEASED"],
                ["BMP3040Z", "Plate outline", "265 x 365 x 1.6", "OFFICIAL"],
                ["BMP3040Z", "Existing hole pitch", "228 x 325", "OFFICIAL"],
                ["X-Lok CC-03RMFS-QC800P", "Panel D-cut", "20.8 / 19.4", "OFFICIAL"],
                ["Phoenix 1237436", "Panel thread/cut", "M16 x 1.5 / 16.2", "VERIFY CUT ON SAMPLE"],
                ["MPPT pictured unit", "Outline", "134 x 70", "VERIFY PHYSICAL UNIT"],
                ["MPPT pictured unit", "Hole pitch", "126 x 50", "VERIFY PHYSICAL UNIT"],
            ]
        )


def main() -> None:
    CAD_DIR.mkdir(exist_ok=True)
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    generate_mounting_plate()
    generate_panel_cutouts()
    print("generated enclosure DXF/SVG files")


if __name__ == "__main__":
    main()
