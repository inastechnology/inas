#!/usr/bin/env python3
"""Generate and finalize the Rev A four-layer KiCad PCB.

This script is intended to run with KiCad's bundled Python interpreter because
it uses the pcbnew SWIG API.  It stages local footprint libraries on the
Windows filesystem to avoid the KiCad footprint plug-in's UNC-path limitation,
then copies the resulting board and Specctra DSN back into the repository.

The initial board contains reviewed placement, the complete netlist, planes,
antenna keep-out, high-current fixed routing, and all mechanical features.
Signal routing is completed by importing a Specctra SES file with --import-ses.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import shutil
import sys
import tempfile
from pathlib import Path

import pcbnew


ROOT = Path(__file__).resolve().parents[1]
STEM = "esp32c6-solar-controller"
PCB_PATH = ROOT / f"{STEM}.kicad_pcb"
DSN_PATH = ROOT / "exports" / f"{STEM}.dsn"
SYSTEM_FP_ROOT = Path(sys.executable).resolve().parents[1] / "share" / "kicad" / "footprints"
LOCAL_LIBRARIES = {
    "INA_CUSTOM": ROOT / "INA_CUSTOM.pretty",
    "INA_ESP32C6": ROOT / "INA_ESP32C6.pretty",
}
BOARD_LEFT = 20.0
BOARD_TOP = 20.0
BOARD_RIGHT = 200.0
BOARD_BOTTOM = 135.0
MOUNTING_HOLES = (
    (24.0, 24.0),
    (196.0, 24.0),
    (24.0, 131.0),
    (196.0, 131.0),
)
TOP_CONNECTOR_X = (40.7, 54.3, 77.7, 101.1, 124.5, 142.8, 156.0, 169.2, 182.4)
OUTPUT_X = (38.0, 74.0, 110.0, 146.0, 182.0)
OUTPUT_CONNECTOR_Y = 129.515


def mm(value: float) -> int:
    return pcbnew.FromMM(value)


def point(x: float, y: float) -> pcbnew.VECTOR2I:
    return pcbnew.VECTOR2I_MM(x, y)


def load_contract():
    path = ROOT / "tools" / "generate_schematic.py"
    spec = importlib.util.spec_from_file_location("ina_generate_schematic", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_placements() -> dict[str, tuple[float, float, float]]:
    """Return explicit, deterministic, non-overlapping Rev A placements."""
    p: dict[str, tuple[float, float, float]] = {
        # Top-edge field connectors.
        "J1": (TOP_CONNECTOR_X[0], 25.21, 0.0),
        "J2": (TOP_CONNECTOR_X[1], 25.0, 0.0),
        "J3": (TOP_CONNECTOR_X[2], 25.0, 0.0),
        "J4": (TOP_CONNECTOR_X[3], 25.0, 0.0),
        "J5": (TOP_CONNECTOR_X[4], 25.0, 0.0),
        "J6": (TOP_CONNECTOR_X[5], 25.0, 0.0),
        "J7": (TOP_CONNECTOR_X[6], 25.0, 0.0),
        "J8": (TOP_CONNECTOR_X[7], 25.0, 0.0),
        "J9": (TOP_CONNECTOR_X[8], 25.0, 0.0),
        # Input protection, buck converter, and battery measurement.
        "F1": (42.0, 55.0, 0.0),
        "Q1": (59.0, 55.0, 0.0),
        "U13": (40.0, 66.0, 0.0),
        "C6": (32.0, 66.0, 0.0),
        "C13": (48.0, 65.0, 0.0),
        "D1": (72.0, 56.0, 0.0),
        "C1": (82.0, 58.0, 0.0),
        "U4": (66.0, 72.0, 0.0),
        "L1": (78.0, 72.0, 0.0),
        "C7": (71.0, 65.5, 0.0),
        "C8": (58.0, 80.0, 0.0),
        "C9": (70.0, 80.0, 0.0),
        "C10": (81.0, 80.0, 0.0),
        "F2": (86.0, 72.0, 0.0),
        "C2": (88.0, 80.0, 0.0),
        "R1": (30.0, 75.0, 0.0),
        "R2": (38.0, 75.0, 0.0),
        "R3": (46.0, 75.0, 0.0),
        "C3": (46.0, 81.0, 0.0),
        "D3": (53.0, 77.0, 0.0),
        # Direct-GPIO controller.  U1 uses the official 24-pad SMD pattern so
        # its four underside JTAG pads are available as application GPIO.
        "U1": (100.0, 62.0, 0.0),
        "R8": (100.0, 76.5, 0.0),
        # RS485 and field power.
        "F3": (116.0, 40.0, 0.0),
        "C11": (115.0, 47.0, 0.0),
        "U3": (123.0, 59.0, 0.0),
        "C5": (116.0, 55.0, 0.0),
        "R9": (116.0, 61.0, 0.0),
        "R10": (132.0, 56.0, 0.0),
        "R11": (132.0, 62.0, 0.0),
        "D2": (140.0, 59.0, 0.0),
        "R12": (136.0, 67.0, 0.0),
        "JP1": (146.0, 66.5, 0.0),
        "R13": (136.0, 72.0, 0.0),
        "R14": (146.0, 72.0, 0.0),
        # Flow input.
        "U12": (134.0, 53.0, 0.0),
        "R16": (127.0, 42.0, 0.0),
        "R17": (127.0, 47.0, 0.0),
        "C12": (127.0, 51.0, 0.0),
        "R18": (137.5, 42.0, 0.0),
        "R19": (137.5, 47.0, 0.0),
        "D34": (124.5, 38.0, 0.0),
        # Input Schmitt trigger.
        "U11": (171.0, 68.0, 0.0),
        "C24": (178.0, 68.0, 0.0),
        # Hard safety gates and gate drivers.
        "U5": (114.0, 79.0, 90.0),
        "U6": (126.0, 79.0, 90.0),
        "C30": (114.0, 73.5, 0.0),
        "C31": (126.0, 73.5, 0.0),
        "U7": (139.0, 79.0, 0.0),
        "U8": (150.0, 79.0, 0.0),
        "U9": (161.0, 79.0, 0.0),
        "C32": (136.5, 73.5, 0.0),
        "C33": (147.5, 73.5, 0.0),
        "C34": (158.5, 73.5, 0.0),
        "C35": (141.5, 73.5, 0.0),
        "C36": (152.5, 73.5, 0.0),
        "C37": (163.5, 73.5, 0.0),
    }

    # Four generic contact inputs, placed below their matching connector.
    for index, x in enumerate(TOP_CONNECTOR_X[5:]):
        p[f"R{20 + index * 2}"] = (x, 40.0, 0.0)
        p[f"R{21 + index * 2}"] = (x + 5.0, 44.0, 0.0)
        p[f"C{20 + index}"] = (x, 48.0, 0.0)
        p[f"D{30 + index}"] = (x + 5.0, 52.0, 0.0)

    # Five identical output channels.  Right-angle connector mating faces sit
    # at the board edge and the power components stay north of their bodies.
    for index, x in enumerate(OUTPUT_X, start=1):
        p[f"F{9 + index}"] = (x, 88.0, 0.0)
        p[f"R{39 + index}"] = (x - 12.0, 96.0, 0.0)
        p[f"R{49 + index}"] = (x - 12.0, 99.5, 0.0)
        p[f"R{54 + index}"] = (x - 12.0, 103.0, 0.0)
        p[f"Q{1 + index}"] = (x - 5.0, 99.5, 180.0)
        p[f"D{9 + index}"] = (x + 9.0, 98.5, 0.0)
        p[f"D{19 + index}"] = (
            (x + 14.5, 88.0, 0.0) if index < 5 else (x, 82.0, 0.0)
        )
        p[f"J{9 + index}"] = (x, OUTPUT_CONNECTOR_Y, 180.0)

    return p


class BoardBuilder:
    def __init__(self, contract, stage: Path):
        self.contract = contract
        self.stage = stage
        self.board = pcbnew.BOARD()
        self.io = pcbnew.PCB_IO_KICAD_SEXPR()
        self.nets: dict[str, pcbnew.NETINFO_ITEM] = {}
        self.footprints: dict[str, pcbnew.FOOTPRINT] = {}
        self.fixed_tracks: list[pcbnew.PCB_TRACK] = []
        self.vias: list[pcbnew.PCB_VIA] = []
        self.placements = build_placements()

    def configure_board(self) -> None:
        self.board.SetCopperLayerCount(4)
        settings = self.board.GetDesignSettings()
        settings.SetBoardThickness(mm(1.6))
        settings.m_MinClearance = mm(0.20)
        settings.m_TrackMinWidth = mm(0.20)
        settings.m_ViasMinSize = mm(0.60)
        settings.m_ViasMinAnnularWidth = mm(0.10)
        settings.m_HoleClearance = mm(0.25)
        settings.m_CopperEdgeClearance = mm(0.30)
        settings.m_MinSilkTextHeight = mm(0.70)
        settings.m_MinSilkTextThickness = mm(0.10)
        settings.SetAuxOrigin(point(BOARD_LEFT, BOARD_TOP))

        net_settings = settings.m_NetSettings
        default = net_settings.GetDefaultNetclass()
        default.SetClearance(mm(0.20))
        default.SetTrackWidth(mm(0.25))
        default.SetViaDiameter(mm(0.80))
        default.SetViaDrill(mm(0.40))

        classes = {
            "LOGIC_POWER": (0.20, 0.50, 0.80, 0.40),
            "FIELD": (0.25, 0.75, 1.00, 0.50),
            "POWER_10A": (0.35, 4.00, 1.20, 0.60),
            "POWER_20A": (0.40, 6.00, 1.20, 0.60),
        }
        for name, (clearance, width, via, drill) in classes.items():
            netclass = pcbnew.NETCLASS(name)
            netclass.SetClearance(mm(clearance))
            netclass.SetTrackWidth(mm(width))
            netclass.SetViaDiameter(mm(via))
            netclass.SetViaDrill(mm(drill))
            net_settings.SetNetclass(name, netclass)

        assignments = {
            "LOGIC_POWER": {"3V3", "5V_RAW", "5V_LOGIC", "BUCK_SW", "BUCK_BST"},
            "FIELD": {"12V_FIELD", "RS485_A", "RS485_B", "RS485_A_LOCAL", "RS485_B_LOCAL"},
            "POWER_20A": {"LOAD_POS", "VIN_FUSED", "12V_ACT"},
            "POWER_10A": {
                *(f"OUT{i}_POS" for i in range(1, 6)),
                *(f"OUT{i}_SW" for i in range(1, 6)),
            },
        }
        for class_name, net_names in assignments.items():
            for net_name in net_names:
                net_settings.SetNetclassPatternAssignment(net_name, class_name)
        net_settings.RecomputeEffectiveNetclasses()

        title = self.board.GetTitleBlock()
        title.SetTitle("INA ESP32-C6 Solar Fertigation Controller")
        title.SetCompany("INA Technologies")
        title.SetRevision("REV A")
        title.SetComment(0, "ORDERABLE ENGINEERING BUILD - VALIDATE BEFORE FIELD USE")
        title.SetComment(1, "12 V loads <100 W; one normal, two maximum")

    def create_nets(self) -> None:
        names = sorted(
            {
                net_name
                for component in self.contract.COMPONENTS
                for net_name in component.nets.values()
                if net_name
            }
        )
        for name in names:
            net = pcbnew.NETINFO_ITEM(self.board, name)
            self.board.Add(net)
            self.nets[name] = net

    def footprint_library_path(self, nickname: str) -> Path:
        if nickname in LOCAL_LIBRARIES:
            return self.stage / f"{nickname}.pretty"
        return SYSTEM_FP_ROOT / f"{nickname}.pretty"

    def load_footprint(self, footprint_id: str) -> pcbnew.FOOTPRINT:
        if ":" not in footprint_id:
            raise ValueError(f"invalid footprint id: {footprint_id}")
        nickname, name = footprint_id.split(":", 1)
        library = self.footprint_library_path(nickname)
        footprint = self.io.FootprintLoad(str(library), name, False)
        if footprint is None:
            raise RuntimeError(f"cannot load {footprint_id} from {library}")
        return footprint

    def add_components(self) -> None:
        contract_refs = {component.ref for component in self.contract.COMPONENTS}
        missing = sorted(contract_refs - self.placements.keys())
        extra = sorted(self.placements.keys() - contract_refs)
        if missing or extra:
            raise RuntimeError(f"placement mismatch: missing={missing}, extra={extra}")

        for component in self.contract.COMPONENTS:
            if not component.footprint:
                raise RuntimeError(f"{component.ref} has no footprint")
            footprint = self.load_footprint(component.footprint)
            footprint.SetReference(component.ref)
            value = component.value + (" [DNP]" if component.dnp else "")
            footprint.SetValue(value)
            footprint.SetDNP(component.dnp)
            footprint.SetExcludedFromPosFiles(component.assembly != "SMT")
            x, y, rotation = self.placements[component.ref]
            footprint.SetPosition(point(x, y))
            footprint.SetOrientationDegrees(rotation)
            self.board.Add(footprint)
            self.footprints[component.ref] = footprint

            seen_numbers: set[str] = set()
            for pad in footprint.Pads():
                number = pad.GetNumber()
                if not number:
                    continue
                if component.footprint == self.contract.FP_PC5_2:
                    # The three high-current holes per potential intentionally
                    # share copper but retain individual solder-mask openings.
                    pad.SetLocalSolderMaskMargin(mm(-0.65))
                seen_numbers.add(number)
                if number not in component.nets:
                    raise RuntimeError(
                        f"{component.ref}: footprint {component.footprint} has unexpected pad {number}"
                    )
                net_name = component.nets[number]
                if net_name:
                    pad.SetNet(self.nets[net_name])
            expected_numbers = {number for number in component.nets if number}
            if not expected_numbers.issubset(seen_numbers):
                absent = sorted(expected_numbers - seen_numbers)
                raise RuntimeError(f"{component.ref}: missing footprint pads {absent}")

            try:
                footprint.Value().SetVisible(False)
                footprint.Reference().SetLayer(pcbnew.F_Fab)
                footprint.Reference().SetVisible(True)
            except AttributeError:
                pass

    def add_mounting_holes(self) -> None:
        for index, (x, y) in enumerate(MOUNTING_HOLES, start=1):
            footprint = self.load_footprint("MountingHole:MountingHole_3.2mm_M3")
            footprint.SetReference(f"H{index}")
            footprint.SetValue("M3 MOUNT")
            footprint.SetPosition(point(x, y))
            self.board.Add(footprint)
            self.footprints[f"H{index}"] = footprint
            try:
                footprint.Value().SetVisible(False)
                footprint.Reference().SetLayer(pcbnew.F_Fab)
                footprint.Reference().SetVisible(True)
            except AttributeError:
                pass

    def add_edge_segment(self, start: tuple[float, float], end: tuple[float, float]) -> None:
        shape = pcbnew.PCB_SHAPE(self.board)
        shape.SetShape(pcbnew.SHAPE_T_SEGMENT)
        shape.SetStart(point(*start))
        shape.SetEnd(point(*end))
        shape.SetLayer(pcbnew.Edge_Cuts)
        shape.SetWidth(mm(0.05))
        self.board.Add(shape)

    def add_board_outline(self) -> None:
        corners = (
            (BOARD_LEFT, BOARD_TOP),
            (BOARD_RIGHT, BOARD_TOP),
            (BOARD_RIGHT, BOARD_BOTTOM),
            (BOARD_LEFT, BOARD_BOTTOM),
        )
        for start, end in zip(corners, corners[1:] + corners[:1]):
            self.add_edge_segment(start, end)

    def add_text(
        self,
        text: str,
        x: float,
        y: float,
        *,
        size: float = 1.2,
        layer: int = pcbnew.F_SilkS,
        angle: float = 0.0,
    ) -> None:
        item = pcbnew.PCB_TEXT(self.board)
        item.SetText(text)
        item.SetPosition(point(x, y))
        item.SetTextSize(point(size, size))
        item.SetTextThickness(mm(max(0.15, size * 0.15)))
        item.SetTextAngleDegrees(angle)
        item.SetLayer(layer)
        if layer == pcbnew.B_SilkS:
            item.SetMirrored(True)
        self.board.Add(item)

    def add_silkscreen(self) -> None:
        self.add_text("INA REV A", 188.0, 75.0, size=1.2, angle=90.0)
        self.add_text("12V / <100W / MAX2", 192.0, 75.0, size=0.8, angle=90.0)
        self.add_text("POWER IN", 42.0, 48.5, size=1.0)
        self.add_text("RS485 / FIELD", 91.0, 37.0, size=0.9)
        self.add_text("SAFETY INPUTS", 166.0, 36.5, size=0.9)
        for index, x in enumerate(OUTPUT_X, start=1):
            self.add_text(f"OUT {index}", x, 108.0, size=0.9)
        self.add_text(
            "ENGINEERING BUILD - BENCH VALIDATE BEFORE FIELD USE",
            110.0,
            106.5,
            size=0.8,
            layer=pcbnew.B_SilkS,
        )

    def add_zone(
        self,
        net_name: str,
        layer: int,
        bounds: tuple[float, float, float, float],
        *,
        clearance: float = 0.30,
        min_thickness: float = 0.25,
        priority: int = 0,
    ) -> pcbnew.ZONE:
        left, top, right, bottom = bounds
        zone = pcbnew.ZONE(self.board)
        zone.SetLayer(layer)
        zone.SetNet(self.nets[net_name])
        zone.SetLocalClearance(mm(clearance))
        zone.SetMinThickness(mm(min_thickness))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_FULL)
        zone.SetAssignedPriority(priority)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        outline = zone.Outline()
        outline.NewOutline()
        for x, y in ((left, top), (right, top), (right, bottom), (left, bottom)):
            outline.Append(point(x, y))
        self.board.Add(zone)
        return zone

    def add_planes(self) -> None:
        bounds = (BOARD_LEFT + 0.6, BOARD_TOP + 0.6, BOARD_RIGHT - 0.6, BOARD_BOTTOM - 0.6)
        self.add_zone("GND", pcbnew.In1_Cu, bounds, clearance=0.25, priority=1)
        self.add_zone("12V_ACT", pcbnew.In2_Cu, bounds, clearance=0.35, priority=1)
        self.add_zone("GND", pcbnew.B_Cu, bounds, clearance=0.25, priority=0)

    def add_antenna_keepout(self) -> None:
        # XIAO antenna end is at local -Y.  The official SMD land pattern has
        # usable GPIO pads beneath the module near this end, so the host-board
        # keepout starts at the module edge and extends into free space.  This
        # preserves an escape path from pads 15/16 without putting host copper
        # in front of the antenna projection.
        zone = pcbnew.ZONE(self.board)
        zone.SetIsRuleArea(True)
        zone.SetLayerSet(pcbnew.LSET.AllCuMask(4))
        zone.SetDoNotAllowTracks(True)
        zone.SetDoNotAllowVias(True)
        zone.SetDoNotAllowZoneFills(True)
        zone.SetDoNotAllowPads(False)
        zone.SetDoNotAllowFootprints(False)
        outline = zone.Outline()
        outline.NewOutline()
        # Keep the central antenna projection clear while leaving both outer
        # pin rows and the official underside land pattern reachable.
        u1_x, u1_y, _ = self.placements["U1"]
        for x, y in (
            (u1_x - 6.5, u1_y - 17.5),
            (u1_x + 6.5, u1_y - 17.5),
            (u1_x + 6.5, u1_y - 10.7),
            (u1_x - 6.5, u1_y - 10.7),
        ):
            outline.Append(point(x, y))
        self.board.Add(zone)

    def pads(self, ref: str, number: str) -> list[pcbnew.PAD]:
        return [pad for pad in self.footprints[ref].Pads() if pad.GetNumber() == str(number)]

    @staticmethod
    def pad_area(pad: pcbnew.PAD) -> int:
        size = pad.GetSize()
        return size.x * size.y

    def largest_pad(self, ref: str, number: str) -> pcbnew.PAD:
        pads = self.pads(ref, number)
        if not pads:
            raise RuntimeError(f"{ref}: no pad {number}")
        return max(pads, key=self.pad_area)

    def closest_pad(self, ref: str, number: str, target: pcbnew.VECTOR2I) -> pcbnew.PAD:
        pads = self.pads(ref, number)
        if not pads:
            raise RuntimeError(f"{ref}: no pad {number}")
        return min(
            pads,
            key=lambda pad: (pad.GetPosition().x - target.x) ** 2
            + (pad.GetPosition().y - target.y) ** 2,
        )

    def add_track(
        self,
        net_name: str,
        start: pcbnew.VECTOR2I,
        end: pcbnew.VECTOR2I,
        width: float,
        *,
        layer: int = pcbnew.F_Cu,
        locked: bool = True,
    ) -> pcbnew.PCB_TRACK:
        if start == end:
            raise ValueError(f"zero-length track on {net_name}")
        track = pcbnew.PCB_TRACK(self.board)
        track.SetNet(self.nets[net_name])
        track.SetLayer(layer)
        track.SetWidth(mm(width))
        track.SetStart(start)
        track.SetEnd(end)
        track.SetLocked(locked)
        self.board.Add(track)
        self.fixed_tracks.append(track)
        return track

    def add_path(
        self,
        net_name: str,
        points: list[pcbnew.VECTOR2I],
        width: float,
        *,
        layer: int = pcbnew.F_Cu,
        locked: bool = True,
    ) -> None:
        for start, end in zip(points, points[1:]):
            if start != end:
                self.add_track(net_name, start, end, width, layer=layer, locked=locked)

    def add_via(
        self,
        net_name: str,
        x: float,
        y: float,
        *,
        diameter: float = 1.0,
        drill: float = 0.5,
        locked: bool = True,
    ) -> pcbnew.PCB_VIA:
        via = pcbnew.PCB_VIA(self.board)
        via.SetNet(self.nets[net_name])
        via.SetPosition(point(x, y))
        via.SetWidth(mm(diameter))
        via.SetDrill(mm(drill))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetLocked(locked)
        self.board.Add(via)
        self.vias.append(via)
        return via

    def add_escape_via(
        self,
        ref: str,
        number: str,
        net_name: str,
        *,
        distance: float = 2.0,
        width: float = 0.25,
    ) -> pcbnew.PCB_VIA:
        """Escape an SMD pad away from its package body and drop to B.Cu."""

        pad = self.largest_pad(ref, number)
        pad_pos = pad.GetPosition()
        centre = self.footprints[ref].GetPosition()
        dx = pcbnew.ToMM(pad_pos.x - centre.x)
        dy = pcbnew.ToMM(pad_pos.y - centre.y)
        magnitude = math.hypot(dx, dy)
        if magnitude == 0:
            raise RuntimeError(f"{ref} pad {number}: cannot determine escape direction")
        via = self.add_via(
            net_name,
            pcbnew.ToMM(pad_pos.x) + distance * dx / magnitude,
            pcbnew.ToMM(pad_pos.y) + distance * dy / magnitude,
            diameter=0.8,
            drill=0.4,
        )
        self.add_track(net_name, pad_pos, via.GetPosition(), width)
        return via

    def connect_duplicate_pads(self, ref: str, number: str, width: float) -> None:
        pads = self.pads(ref, number)
        if len(pads) < 2:
            return
        net_name = pads[0].GetNetname()
        connected = [pads[0]]
        remaining = pads[1:]
        while remaining:
            best: tuple[int, pcbnew.PAD, pcbnew.PAD] | None = None
            for source in connected:
                for target in remaining:
                    a = source.GetPosition()
                    b = target.GetPosition()
                    distance = (a.x - b.x) ** 2 + (a.y - b.y) ** 2
                    if best is None or distance < best[0]:
                        best = (distance, source, target)
            assert best is not None
            _, source, target = best
            self.add_track(net_name, source.GetPosition(), target.GetPosition(), width)
            connected.append(target)
            remaining.remove(target)

    def add_high_current_routing(self) -> None:
        # Parallel mechanical pins share current; explicitly stitch them in
        # copper so every pin contributes and DRC sees a continuous conductor.
        for ref in ("J1", "J10", "J11", "J12", "J13", "J14"):
            self.connect_duplicate_pads(ref, "1", 3.0)
            self.connect_duplicate_pads(ref, "2", 3.0)
        for ref in ("F1", "F10", "F11", "F12", "F13", "F14"):
            self.connect_duplicate_pads(ref, "1", 2.5)
            self.connect_duplicate_pads(ref, "2", 2.5)

        # Input connector to fuse.
        j1_pos = max(self.pads("J1", "1"), key=lambda pad: pad.GetPosition().y)
        f1_in = min(
            self.pads("F1", "1"),
            key=lambda pad: (pad.GetPosition().x - j1_pos.GetPosition().x) ** 2
            + (pad.GetPosition().y - j1_pos.GetPosition().y) ** 2,
        )
        self.add_track("LOAD_POS", j1_pos.GetPosition(), f1_in.GetPosition(), 6.0)

        # Input fuse to the three MOSFET source lands, using narrow final
        # fingers to avoid the adjacent gate land.
        source_pads = self.pads("Q1", "3")
        source_y = sum(pad.GetPosition().y for pad in source_pads) // len(source_pads)
        source_bus = point(54.0, pcbnew.ToMM(source_y))
        for pad in source_pads:
            self.add_track("VIN_FUSED", pad.GetPosition(), source_bus, 0.75)
        f1_out = self.closest_pad("F1", "2", source_bus)
        self.add_track("VIN_FUSED", f1_out.GetPosition(), source_bus, 4.0)

        # Drain of reverse-polarity MOSFET to the 12V inner plane.
        q1_drain = self.largest_pad("Q1", "2").GetPosition()
        for x in (64.0, 66.0, 68.0):
            for y in (52.5, 55.0, 57.5):
                via = self.add_via("12V_ACT", x, y, diameter=1.2, drill=0.6)
                self.add_track("12V_ACT", q1_drain, via.GetPosition(), 2.0)

        # Five output branches.
        for index, x in enumerate(OUTPUT_X, start=1):
            fuse = f"F{9 + index}"
            mosfet = f"Q{1 + index}"
            diode = f"D{9 + index}"
            tvs = f"D{19 + index}"
            connector = f"J{9 + index}"
            pos_net = f"OUT{index}_POS"
            sw_net = f"OUT{index}_SW"

            connector_pos = min(self.pads(connector, "1"), key=lambda pad: pad.GetPosition().y)
            connector_sw = min(self.pads(connector, "2"), key=lambda pad: pad.GetPosition().y)
            fuse_out = max(
                self.pads(fuse, "2"),
                key=lambda pad: (pad.GetPosition().x, pad.GetPosition().y),
            )
            pos_top = point(x + 7.0, 92.0)
            pos_bottom = point(x + 7.0, 108.0)
            self.add_path(
                pos_net,
                [fuse_out.GetPosition(), pos_top, pos_bottom, connector_pos.GetPosition()],
                4.0,
            )

            drain = self.largest_pad(mosfet, "2")
            self.add_track(sw_net, drain.GetPosition(), connector_sw.GetPosition(), 4.0)

            # The D2PAK cathode tab intersects the +12 V trunk.  Also connect
            # its lead explicitly; route the anode left into the switched
            # return while maintaining clearance from the positive trunk.
            diode_k = min(self.pads(diode, "1"), key=self.pad_area)
            diode_a = self.largest_pad(diode, "2")
            pos_anchor = point(x + 7.0, pcbnew.ToMM(diode_k.GetPosition().y))
            sw_anchor = point(x - 3.81, pcbnew.ToMM(diode_a.GetPosition().y))
            self.add_track(pos_net, diode_k.GetPosition(), pos_anchor, 2.0)
            self.add_path(
                sw_net,
                [diode_a.GetPosition(), sw_anchor, drain.GetPosition()],
                2.0,
            )

            # Pre-route the optional output TVS footprint as well.  Although
            # D20..D24 are DNP by default, leaving them electrically open makes
            # the autorouter add redundant branches beside the 4 mm trunk.
            tvs_sw = self.largest_pad(tvs, "1")
            tvs_gnd = self.largest_pad(tvs, "2")
            tvs_sw_via = self.add_escape_via(
                tvs,
                "1",
                sw_net,
                distance=2.0,
                width=0.75,
            )
            tie_position = pcbnew.VECTOR2I(
                (drain.GetPosition().x + connector_sw.GetPosition().x) // 2,
                (drain.GetPosition().y + connector_sw.GetPosition().y) // 2,
            )
            sw_tie_via = self.add_via(
                sw_net,
                pcbnew.ToMM(tie_position.x),
                pcbnew.ToMM(tie_position.y),
                diameter=1.0,
                drill=0.5,
            )
            tvs_corridor_x = min(x + 18.0, BOARD_RIGHT - 4.0)
            self.add_path(
                sw_net,
                [
                    tvs_sw_via.GetPosition(),
                    point(tvs_corridor_x, pcbnew.ToMM(tvs_sw.GetPosition().y)),
                    point(tvs_corridor_x, 110.0),
                    sw_tie_via.GetPosition(),
                ],
                0.75,
                layer=pcbnew.B_Cu,
            )
            tvs_gnd_via = self.add_via(
                "GND",
                pcbnew.ToMM(tvs_gnd.GetPosition().x),
                pcbnew.ToMM(tvs_gnd.GetPosition().y) - 3.0,
                diameter=1.0,
                drill=0.5,
            )
            self.add_track("GND", tvs_gnd.GetPosition(), tvs_gnd_via.GetPosition(), 0.75)

            # Three source fingers each get a dedicated via into the GND plane.
            for pad in self.pads(mosfet, "3"):
                px = pcbnew.ToMM(pad.GetPosition().x)
                py = pcbnew.ToMM(pad.GetPosition().y)
                via = self.add_via("GND", px, py - 3.2, diameter=1.0, drill=0.5)
                self.add_track("GND", pad.GetPosition(), via.GetPosition(), 0.8)

    def add_manual_escape_routing(self) -> None:
        """Lock critical local power routes before handing signals to the router."""

        # The compact gate-driver row can split the F.Cu ground pour into a
        # narrow island around U8.  Give that pad an explicit path to the
        # continuous inner ground plane rather than relying on zone geometry.
        self.add_escape_via("U8", "3", "GND", distance=1.2, width=0.4)

        self.add_escape_via(
            "U13",
            "8",
            "12V_ACT",
            distance=1.2,
            width=0.5,
        )
        c13_p2 = self.largest_pad("C13", "2").GetPosition()
        c13_via = self.add_via("12V_ACT", 51.0, 65.0, diameter=1.2, drill=0.6)
        self.add_track("12V_ACT", c13_p2, c13_via.GetPosition(), 0.5)

        u4_plane_via = self.add_via("12V_ACT", 61.5, 75.0, diameter=1.2, drill=0.6)
        for number in ("2", "3"):
            self.add_track(
                "12V_ACT",
                self.largest_pad("U4", number).GetPosition(),
                u4_plane_via.GetPosition(),
                0.5,
            )

        # AP63205 input/output loop.
        self.add_track(
            "12V_ACT",
            self.largest_pad("C8", "1").GetPosition(),
            u4_plane_via.GetPosition(),
            0.5,
        )
        buck_5v = self.add_escape_via("U4", "1", "5V_RAW", width=0.5)
        inductor_5v = self.add_escape_via("L1", "2", "5V_RAW", width=0.5)
        self.add_path(
            "5V_RAW",
            [
                buck_5v.GetPosition(),
                point(62.0, 68.0),
                point(83.0, 68.0),
                inductor_5v.GetPosition(),
            ],
            0.5,
            layer=pcbnew.B_Cu,
        )

        # LM74610-Q1 charge-pump and gate loop.  These short, local routes are
        # electrically critical and are kept out of the autorouter's search.
        c6_vcaph = self.add_escape_via("C6", "1", "RPOL_VCAPH")
        u13_vcaph = self.add_escape_via("U13", "7", "RPOL_VCAPH")
        self.add_path(
            "RPOL_VCAPH",
            [
                c6_vcaph.GetPosition(),
                point(34.0, 59.0),
                u13_vcaph.GetPosition(),
            ],
            0.25,
            layer=pcbnew.B_Cu,
        )

        u13_vin = self.add_escape_via("U13", "4", "VIN_FUSED", width=0.5)
        c13_vin = self.add_escape_via("C13", "1", "VIN_FUSED", width=0.5)
        self.add_track(
            "VIN_FUSED",
            u13_vin.GetPosition(),
            c13_vin.GetPosition(),
            0.5,
            layer=pcbnew.B_Cu,
        )
        source_pads = self.pads("Q1", "3")
        source_y = sum(pad.GetPosition().y for pad in source_pads) // len(source_pads)
        source_bus = point(54.0, pcbnew.ToMM(source_y))
        c13_via_x = pcbnew.ToMM(c13_vin.GetPosition().x)
        self.add_path(
            "VIN_FUSED",
            [
                c13_vin.GetPosition(),
                point(c13_via_x, 70.0),
                point(54.0, 70.0),
                source_bus,
            ],
            0.5,
            layer=pcbnew.F_Cu,
        )

        q1_gate_via = self.add_escape_via("Q1", "1", "RPOL_GATE")
        u13_gate_via = self.add_escape_via("U13", "6", "RPOL_GATE")
        self.add_path(
            "RPOL_GATE",
            [
                u13_gate_via.GetPosition(),
                point(48.0, 60.5),
                q1_gate_via.GetPosition(),
            ],
            0.25,
            layer=pcbnew.B_Cu,
        )

        # Tie the ESP32 module and the last gate-driver island into the shared
        # protected 5 V rail.  The back-layer trunk stays below the antenna
        # keepout; local vias avoid via-in-pad assembly.
        f2_5v = self.largest_pad("F2", "2").GetPosition()
        f2_via = self.add_via(
            "5V_LOGIC",
            pcbnew.ToMM(f2_5v.x) + 2.0,
            pcbnew.ToMM(f2_5v.y),
            diameter=0.8,
            drill=0.4,
        )
        self.add_track("5V_LOGIC", f2_5v, f2_via.GetPosition(), 0.5)
        u1_5v = self.add_escape_via("U1", "14", "5V_LOGIC", width=0.5)
        self.add_path(
            "5V_LOGIC",
            [
                f2_via.GetPosition(),
                point(92.0, 52.0),
                point(111.0, 52.0),
                point(111.0, pcbnew.ToMM(u1_5v.GetPosition().y)),
                u1_5v.GetPosition(),
            ],
            0.5,
            layer=pcbnew.B_Cu,
        )

        # A fixed 3V3 back-layer spine prevents the autorouter from splitting
        # the low-current logic rail into separate islands around the dense
        # contact-input section.
        u1_3v3 = self.add_escape_via("U1", "12", "3V3")
        self.add_track(
            "3V3",
            self.largest_pad("U1", "22").GetPosition(),
            self.largest_pad("U1", "12").GetPosition(),
            0.25,
        )
        c5_3v3 = self.add_escape_via("C5", "1", "3V3")
        u12_3v3 = self.add_escape_via("U12", "5", "3V3")
        r18_3v3 = self.add_escape_via("R18", "1", "3V3")
        self.add_path(
            "3V3",
            [
                u1_3v3.GetPosition(),
                point(112.0, 63.0),
                c5_3v3.GetPosition(),
                point(122.0, 50.5),
                u12_3v3.GetPosition(),
                point(138.0, 50.5),
                point(138.0, 42.0),
                r18_3v3.GetPosition(),
            ],
            0.25,
            layer=pcbnew.B_Cu,
        )

        # The two signal layers are dense around the XIAO and comparator.
        # Reserve a deterministic back-layer corridor for the timing-critical
        # flow pulse instead of allowing it to remain as the router's final
        # unrouted connection.
        flow_u1_pad = self.largest_pad("U1", "3").GetPosition()
        flow_u12_pad = self.largest_pad("U12", "1").GetPosition()
        flow_u1_via = self.add_via(
            "FLOW_PULSE",
            90.0,
            pcbnew.ToMM(flow_u1_pad.y),
            diameter=0.8,
            drill=0.4,
        )
        flow_u12_via = self.add_via(
            "FLOW_PULSE",
            130.8,
            pcbnew.ToMM(flow_u12_pad.y),
            diameter=0.8,
            drill=0.4,
        )
        self.add_track(
            "FLOW_PULSE",
            flow_u1_pad,
            flow_u1_via.GetPosition(),
            0.25,
        )
        self.add_track(
            "FLOW_PULSE",
            flow_u12_pad,
            flow_u12_via.GetPosition(),
            0.25,
        )
        self.add_path(
            "FLOW_PULSE",
            [
                flow_u1_via.GetPosition(),
                point(88.0, pcbnew.ToMM(flow_u1_pad.y)),
                point(88.0, 75.0),
                point(125.0, 75.0),
                point(125.0, 55.0),
                point(130.8, 55.0),
                flow_u12_via.GetPosition(),
            ],
            0.25,
            layer=pcbnew.B_Cu,
        )

        c33_5v = self.add_escape_via("C33", "1", "5V_LOGIC", width=0.5)
        c34_5v = self.add_escape_via("C34", "1", "5V_LOGIC", width=0.5)
        u9_5v = self.add_escape_via("U9", "6", "5V_LOGIC", width=0.5)
        self.add_track(
            "5V_LOGIC",
            c33_5v.GetPosition(),
            c34_5v.GetPosition(),
            0.5,
            layer=pcbnew.B_Cu,
        )
        self.add_track(
            "5V_LOGIC",
            c34_5v.GetPosition(),
            u9_5v.GetPosition(),
            0.5,
            layer=pcbnew.B_Cu,
        )

    def add_plane_escape_vias(self) -> None:
        """Give every SMD plane pad an explicit connection to its inner plane.

        Freerouting is intentionally prohibited from using In1.Cu and In2.Cu
        as signal layers.  Through-hole pads already intersect those planes;
        SMD GND and 12V_ACT pads therefore receive short locked fan-outs and
        through-vias before the remaining signals are routed.
        """

        plane_nets = {"GND", "12V_ACT"}
        already_escaped = {
            (track.GetNetname(), track.GetStart().x, track.GetStart().y)
            for track in self.fixed_tracks
        } | {
            (track.GetNetname(), track.GetEnd().x, track.GetEnd().y)
            for track in self.fixed_tracks
        }
        direction_overrides = {
            # Avoid the fixed 3V3 and 5V_LOGIC back-layer spines.
            ("C12", "2"): (0.0, 1.0),
            ("C33", "2"): (0.0, 1.0),
            ("C36", "2"): (0.0, 1.0),
            # Escape perpendicular to adjacent fine-pitch package pads.
            ("U1", "18"): (1.0, 0.0),
            ("U6", "9"): (0.0, -1.0),
            ("U11", "13"): (1.0, 0.0),
        }

        for footprint in self.footprints.values():
            centre = footprint.GetPosition()
            for pad in footprint.Pads():
                net_name = pad.GetNetname()
                pad_pos = pad.GetPosition()
                if (
                    net_name not in plane_nets
                    or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or (net_name, pad_pos.x, pad_pos.y) in already_escaped
                ):
                    continue

                override = direction_overrides.get(
                    (footprint.GetReference(), pad.GetNumber())
                )
                if override:
                    dx, dy = override
                else:
                    dx = pcbnew.ToMM(pad_pos.x - centre.x)
                    dy = pcbnew.ToMM(pad_pos.y - centre.y)
                magnitude = math.hypot(dx, dy)
                if magnitude < 0.01:
                    dx, dy, magnitude = 1.0, 0.0, 1.0
                distance = 1.2
                via_x = pcbnew.ToMM(pad_pos.x) + distance * dx / magnitude
                via_y = pcbnew.ToMM(pad_pos.y) + distance * dy / magnitude
                if not (
                    BOARD_LEFT + 1.0 <= via_x <= BOARD_RIGHT - 1.0
                    and BOARD_TOP + 1.0 <= via_y <= BOARD_BOTTOM - 1.0
                ):
                    raise RuntimeError(
                        f"{footprint.GetReference()} pad {pad.GetNumber()}: "
                        "plane escape would leave board"
                    )
                via = self.add_via(
                    net_name,
                    via_x,
                    via_y,
                    diameter=0.8,
                    drill=0.4,
                )
                self.add_track(net_name, pad_pos, via.GetPosition(), 0.4)

    def fill_zones(self) -> None:
        filler = pcbnew.ZONE_FILLER(self.board)
        if not filler.Fill(self.board.Zones()):
            raise RuntimeError("zone fill failed")

    def add_ground_stitching_vias(self) -> None:
        """Stitch the bottom ground pour to the continuous inner GND plane."""

        def near_component_body(candidate: pcbnew.VECTOR2I) -> bool:
            margin = mm(1.0)
            for footprint in self.footprints.values():
                box = footprint.GetBoundingBox(False, False)
                if (
                    box.GetLeft() - margin <= candidate.x <= box.GetRight() + margin
                    and box.GetTop() - margin <= candidate.y <= box.GetBottom() + margin
                ):
                    return True
            return False

        def occupied(candidate: pcbnew.VECTOR2I) -> bool:
            if near_component_body(candidate):
                return True
            if any(track.HitTest(candidate, mm(1.0)) for track in self.fixed_tracks):
                return True
            return any(via.HitTest(candidate, mm(1.2)) for via in self.vias)

        u1_x, u1_y, _ = self.placements["U1"]
        for x in range(int(BOARD_LEFT + 9), int(BOARD_RIGHT - 9), 15):
            for y in range(int(BOARD_TOP + 9), int(BOARD_BOTTOM - 9), 15):
                # Keep copper and holes out of the ESP32-C6 antenna volume.
                if u1_x - 9.0 <= x <= u1_x + 9.0 and u1_y - 16.0 <= y <= u1_y - 5.0:
                    continue
                candidate = point(float(x), float(y))
                if occupied(candidate):
                    continue
                self.add_via("GND", float(x), float(y), diameter=0.8, drill=0.4)

        # Guaranteed main-plane stitch in the open service-label area.
        self.add_via("GND", 192.0, 76.0, diameter=0.8, drill=0.4)

    def build(self) -> None:
        self.configure_board()
        self.create_nets()
        self.add_components()
        self.add_mounting_holes()
        self.add_board_outline()
        self.add_silkscreen()
        self.add_planes()
        self.add_antenna_keepout()
        self.add_high_current_routing()
        self.add_manual_escape_routing()
        self.add_plane_escape_vias()
        self.add_ground_stitching_vias()
        self.fill_zones()


def stage_local_libraries(stage: Path) -> None:
    for nickname, source in LOCAL_LIBRARIES.items():
        destination = stage / f"{nickname}.pretty"
        shutil.copytree(source, destination)


def save_and_copy(board: pcbnew.BOARD, stage: Path, *, export_dsn: bool) -> None:
    stage_pcb = stage / PCB_PATH.name
    if not pcbnew.SaveBoard(str(stage_pcb), board):
        raise RuntimeError(f"failed to save {stage_pcb}")
    shutil.copy2(stage_pcb, PCB_PATH)
    if export_dsn:
        stage_dsn = stage / DSN_PATH.name
        if not pcbnew.ExportSpecctraDSN(board, str(stage_dsn)):
            raise RuntimeError(f"failed to export {stage_dsn}")
        # KiCad exports every copper layer as a signal layer even when an
        # inner layer is intentionally reserved for a power plane.  Mark the
        # two inner layers as power in the router interchange file so
        # Freerouting cannot cut the continuous GND and 12V_ACT planes.
        dsn_text = stage_dsn.read_text(encoding="utf-8")
        for layer_name in ("In1.Cu", "In2.Cu"):
            signal_declaration = (
                f"    (layer {layer_name}\n"
                "      (type signal)"
            )
            power_declaration = (
                f"    (layer {layer_name}\n"
                "      (type power)"
            )
            if signal_declaration not in dsn_text:
                raise RuntimeError(f"cannot locate DSN layer declaration for {layer_name}")
            dsn_text = dsn_text.replace(
                signal_declaration,
                power_declaration,
                1,
            )
        stage_dsn.write_text(dsn_text, encoding="utf-8")
        DSN_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(stage_dsn, DSN_PATH)


def stitch_filled_ground_islands(board: pcbnew.BOARD) -> int:
    """Add one plane via inside every sufficiently large F.Cu GND polygon."""

    added = 0
    probe_radius = mm(0.60)
    raster_step = mm(0.50)
    routed_items = [
        item
        for item in board.AllConnectedItems()
        if isinstance(item, (pcbnew.PCB_TRACK, pcbnew.PCB_VIA))
    ]
    for zone in list(board.Zones()):
        if zone.GetLayer() != pcbnew.F_Cu or zone.GetNetname() != "GND":
            continue
        polygons = zone.GetFilledPolysList(pcbnew.F_Cu)
        for outline_index in range(polygons.OutlineCount()):
            island = polygons.UnitSet(outline_index)
            box = island.BBox()
            candidates: list[pcbnew.VECTOR2I] = [
                pcbnew.VECTOR2I(
                    (box.GetLeft() + box.GetRight()) // 2,
                    (box.GetTop() + box.GetBottom()) // 2,
                )
            ]
            for y in range(
                box.GetTop() + probe_radius,
                box.GetBottom() - probe_radius + 1,
                raster_step,
            ):
                for x in range(
                    box.GetLeft() + probe_radius,
                    box.GetRight() - probe_radius + 1,
                    raster_step,
                ):
                    candidates.append(pcbnew.VECTOR2I(x, y))

            position = None
            for candidate in candidates:
                # The filled F.Cu polygon has no knowledge of tracks on the
                # inner layers.  Check the complete routed board before
                # committing a through-via.
                if any(item.HitTest(candidate, mm(0.70)) for item in routed_items):
                    continue
                probes = (
                    candidate,
                    pcbnew.VECTOR2I(candidate.x + probe_radius, candidate.y),
                    pcbnew.VECTOR2I(candidate.x - probe_radius, candidate.y),
                    pcbnew.VECTOR2I(candidate.x, candidate.y + probe_radius),
                    pcbnew.VECTOR2I(candidate.x, candidate.y - probe_radius),
                )
                if all(polygons.Contains(probe, outline_index) for probe in probes):
                    position = candidate
                    break
            if position is None:
                continue

            via = pcbnew.PCB_VIA(board)
            via.SetNet(zone.GetNet())
            via.SetPosition(position)
            via.SetWidth(mm(0.8))
            via.SetDrill(mm(0.4))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            via.SetLocked(True)
            board.Add(via)
            added += 1
    return added


def remove_autorouter_artifacts(board: pcbnew.BOARD) -> int:
    """Remove redundant branches left by Freerouting on pre-routed nets.

    The locked high-current routes are generated before the Specctra export.
    Freerouting sometimes duplicates those OUTx_SW trunks with unlocked,
    dead-end branches.  It can also leave a 0.127 mm 3V3 stub beside the fixed
    U12 escape via.  Neither item participates in the intended connectivity.
    """

    removed = 0
    output_nets = {f"OUT{index}_SW" for index in range(1, 6)}
    u12 = next(
        (footprint for footprint in board.GetFootprints() if footprint.GetReference() == "U12"),
        None,
    )
    u12_x = pcbnew.ToMM(u12.GetPosition().x) if u12 else 0.0
    u12_y = pcbnew.ToMM(u12.GetPosition().y) if u12 else 0.0
    for item in list(board.GetTracks()):
        if item.IsLocked():
            continue
        if item.GetNetname() in output_nets:
            board.Remove(item)
            removed += 1
            continue
        if isinstance(item, pcbnew.PCB_VIA):
            continue
        if (
            item.GetNetname() == "3V3"
            and pcbnew.ToMM(item.GetLength()) < 2.0
            and abs(pcbnew.ToMM(item.GetStart().x) - u12_x) <= 3.0
            and abs(pcbnew.ToMM(item.GetEnd().x) - u12_x) <= 3.0
            and abs(pcbnew.ToMM(item.GetStart().y) - u12_y) <= 3.0
            and abs(pcbnew.ToMM(item.GetEnd().y) - u12_y) <= 3.0
        ):
            board.Remove(item)
            removed += 1
            continue
    return removed


def generate_initial() -> None:
    contract = load_contract()
    with tempfile.TemporaryDirectory(prefix="inas-kicad-") as temporary:
        stage = Path(temporary)
        stage_local_libraries(stage)
        builder = BoardBuilder(contract, stage)
        builder.build()
        save_and_copy(builder.board, stage, export_dsn=True)
        print(f"generated {PCB_PATH}")
        print(f"generated {DSN_PATH}")
        print(f"footprints {len(builder.board.GetFootprints())}")
        print(f"nets {len(builder.nets)}")


def import_session(session: Path) -> None:
    if not PCB_PATH.exists():
        raise FileNotFoundError(PCB_PATH)
    if not session.exists():
        raise FileNotFoundError(session)
    with tempfile.TemporaryDirectory(prefix="inas-kicad-") as temporary:
        stage = Path(temporary)
        stage_pcb = stage / PCB_PATH.name
        stage_ses = stage / session.name
        shutil.copy2(PCB_PATH, stage_pcb)
        shutil.copy2(session, stage_ses)
        board = pcbnew.LoadBoard(str(stage_pcb))
        if board is None:
            raise RuntimeError(f"failed to load {stage_pcb}")
        if not pcbnew.ImportSpecctraSES(board, str(stage_ses)):
            raise RuntimeError(f"failed to import {stage_ses}")

        filler = pcbnew.ZONE_FILLER(board)
        if not filler.Fill(board.Zones()):
            raise RuntimeError("zone fill after SES import failed")
        stitched = stitch_filled_ground_islands(board)
        if stitched and not filler.Fill(board.Zones()):
            raise RuntimeError("zone refill after GND island stitching failed")
        removed_artifacts = remove_autorouter_artifacts(board)
        save_and_copy(board, stage, export_dsn=False)
        print(f"imported {session}")
        print(f"removed {removed_artifacts} redundant autorouter artifacts")
        print(f"stitched {stitched} F.Cu GND polygons")
        print(f"updated {PCB_PATH}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--import-ses",
        type=Path,
        help="import a Freerouting Specctra session into the generated board",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.import_ses:
        import_session(args.import_ses.resolve())
    else:
        generate_initial()


if __name__ == "__main__":
    main()
