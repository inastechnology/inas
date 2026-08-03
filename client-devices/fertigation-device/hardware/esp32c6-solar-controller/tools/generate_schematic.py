#!/usr/bin/env python3
"""Generate the revision-1 KiCad schematic from the reviewed hardware contract.

The generated schematic intentionally uses self-contained symbols.  This keeps
the file reproducible on KiCad installations that do not yet have the INA
project symbol library.  Electrical pin types are passive in revision 1 so ERC
checks connectivity and file integrity.  Selected manufacturer parts are
recorded in symbol fields; application-dependent release holds remain explicit.
"""

from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEM = "esp32c6-solar-controller"
SCH_PATH = ROOT / f"{STEM}.kicad_sch"
PRO_PATH = ROOT / f"{STEM}.kicad_pro"
SYM_PATH = ROOT / "INA.kicad_sym"
SYM_TABLE_PATH = ROOT / "sym-lib-table"
FP_DIR = ROOT / "INA_ESP32C6.pretty"
FP_PATH = FP_DIR / "XIAO_ESP32C6_SMD_24P.kicad_mod"
FP_TABLE_PATH = ROOT / "fp-lib-table"
NAMESPACE = uuid.UUID("111bdf69-8dd2-47f4-ad0b-40fa9cf8a617")


def uid(key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, key))


def quoted(value: object) -> str:
    text = str(value)
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def grid(value: float) -> float:
    """Snap schematic connection points to KiCad's 1.27 mm connection grid."""
    return round(value / 1.27) * 1.27


def effects(hidden: bool = False, size: float = 1.27, justify: str = "") -> str:
    hide = "\n\t\t\t(hide yes)" if hidden else ""
    justification = f"\n\t\t\t(justify {justify})" if justify else ""
    return (
        "(effects\n"
        "\t\t\t(font\n"
        f"\t\t\t\t(size {size} {size})\n"
        f"\t\t\t){hide}{justification}\n"
        "\t\t)"
    )


@dataclass(frozen=True)
class Pin:
    number: str
    name: str
    side: str


@dataclass
class SymbolDef:
    name: str
    prefix: str
    pins: list[Pin]
    width: float = 15.24

    @property
    def left(self) -> list[Pin]:
        return [pin for pin in self.pins if pin.side == "L"]

    @property
    def right(self) -> list[Pin]:
        return [pin for pin in self.pins if pin.side == "R"]

    @property
    def height(self) -> float:
        return max(7.62, (max(len(self.left), len(self.right), 1) + 1) * 2.54)

    def positions(self) -> dict[str, tuple[float, float, int]]:
        result: dict[str, tuple[float, float, int]] = {}
        for side, pins in (("L", self.left), ("R", self.right)):
            y0 = -((len(pins) - 1) * 2.54) / 2
            x = -(self.width / 2 + 2.54) if side == "L" else self.width / 2 + 2.54
            angle = 0 if side == "L" else 180
            for index, pin in enumerate(pins):
                result[pin.number] = (x, y0 + index * 2.54, angle)
        return result


DEFS: dict[str, SymbolDef] = {}


def define(name: str, prefix: str, left: list[tuple[str, str]], right: list[tuple[str, str]], width: float = 15.24) -> None:
    pins = [Pin(number, pin_name, "L") for number, pin_name in left]
    pins.extend(Pin(number, pin_name, "R") for number, pin_name in right)
    DEFS[name] = SymbolDef(name, prefix, pins, width)


define("R", "R", [("1", "1")], [("2", "2")], 5.08)
define("C", "C", [("1", "1")], [("2", "2")], 5.08)
define("L", "L", [("1", "1")], [("2", "2")], 5.08)
define("DIODE", "D", [("1", "K")], [("2", "A")], 5.08)
define("ESD2", "D", [("1", "IO")], [("2", "GND")], 5.08)
define("FUSE", "F", [("1", "IN")], [("2", "OUT")], 7.62)
define("JUMPER", "JP", [("1", "1")], [("2", "2")], 7.62)
define("CONN2", "J", [("1", "PIN1"), ("2", "PIN2")], [], 7.62)
define("CONN3", "J", [("1", "PIN1"), ("2", "PIN2"), ("3", "PIN3")], [], 7.62)
define(
    "CONN4",
    "J",
    [("1", "PIN1"), ("2", "PIN2"), ("3", "PIN3"), ("4", "PIN4")],
    [],
    7.62,
)
define(
    "XIAO_ESP32C6",
    "U",
    [
        ("1", "D0_GPIO0"),
        ("2", "D1_GPIO1"),
        ("3", "D2_GPIO2"),
        ("4", "D3_GPIO21"),
        ("5", "D4_GPIO22"),
        ("6", "D5_GPIO23"),
        ("7", "D6_GPIO16_TX"),
        ("15", "MTDI_GPIO5_STRAP"),
        ("16", "MTDO_GPIO7"),
        ("19", "MTMS_GPIO4_STRAP"),
        ("20", "MTCK_GPIO6"),
    ],
    [
        ("8", "D7_GPIO17_RX"),
        ("9", "D8_GPIO19_DIR"),
        ("10", "D9_GPIO20"),
        ("11", "D10_GPIO18"),
        ("12", "3V3"),
        ("13", "GND"),
        ("14", "5V"),
        ("17", "EN"),
        ("18", "GND"),
        ("21", "BOOT"),
        ("22", "3V3"),
        ("23", "VBAT"),
        ("24", "GND"),
    ],
    25.40,
)
define(
    "RS485",
    "U",
    [("1", "R"), ("2", "~RE"), ("3", "DE"), ("4", "D")],
    [("5", "GND"), ("6", "A"), ("7", "B"), ("8", "VCC")],
    15.24,
)
define(
    "QUAD_AND",
    "U",
    [
        ("1", "1A"),
        ("2", "1B"),
        ("3", "1Y"),
        ("4", "2A"),
        ("5", "2B"),
        ("6", "2Y"),
        ("7", "GND"),
    ],
    [
        ("8", "3Y"),
        ("9", "3B"),
        ("10", "3A"),
        ("11", "4Y"),
        ("12", "4B"),
        ("13", "4A"),
        ("14", "VCC"),
    ],
    20.32,
)
define(
    "DUAL_GATE_DRIVER",
    "U",
    [("1", "NC"), ("2", "INA"), ("3", "GND"), ("4", "INB")],
    [("5", "OUTB"), ("6", "VDD"), ("7", "OUTA"), ("8", "NC")],
    15.24,
)
define(
    "HEX_SCHMITT",
    "U",
    [
        ("1", "1A"),
        ("2", "1Y"),
        ("3", "2A"),
        ("4", "2Y"),
        ("5", "3A"),
        ("6", "3Y"),
        ("7", "GND"),
    ],
    [
        ("8", "4Y"),
        ("9", "4A"),
        ("10", "5Y"),
        ("11", "5A"),
        ("12", "6Y"),
        ("13", "6A"),
        ("14", "VCC"),
    ],
    20.32,
)
define("NMOS", "Q", [("1", "G")], [("2", "D"), ("3", "S")], 7.62)
define("SM712", "D", [("1", "LINE_A"), ("2", "LINE_B")], [("3", "COMMON")], 7.62)
define(
    "BAT54S",
    "D",
    [("1", "A1_GND"), ("2", "K2_3V3")],
    [("3", "K1_A2_ADC")],
    7.62,
)
define("POWER_PROTECT", "Q", [("1", "VIN"), ("3", "GND")], [("2", "VOUT")], 12.7)
define(
    "IDEAL_DIODE_CTRL",
    "U",
    [("1", "VCAPL"), ("2", "GATE_PULL_DOWN"), ("3", "NC"), ("4", "ANODE")],
    [("5", "NC"), ("6", "GATE_DRIVE"), ("7", "VCAPH"), ("8", "CATHODE")],
    17.78,
)
define(
    "BUCK5V",
    "U",
    [("1", "FB"), ("2", "EN"), ("3", "VIN")],
    [("4", "GND"), ("5", "SW"), ("6", "BST")],
    12.7,
)
define(
    "FLOW_INPUT",
    "U",
    [("3", "IN+"), ("4", "IN-"), ("2", "GND")],
    [("1", "OUT"), ("5", "VCC")],
    12.7,
)


@dataclass
class Component:
    ref: str
    lib: str
    value: str
    x: float
    y: float
    nets: dict[str, str | None]
    footprint: str = ""
    manufacturer: str = ""
    mpn: str = ""
    lcsc: str = ""
    assembly: str = "SMT"
    dnp: bool = False
    note: str = ""


COMPONENTS: list[Component] = []
NOTES: list[tuple[str, float, float, float]] = []

# The schematic was originally composed to fill an A3 sheet.  Keep the
# authored coordinates compact and readable below, then expand the finished
# drawing onto A1 so symbols, net labels, properties, and section notes have
# comfortable review/annotation space.
SCHEMATIC_ORIGIN_X = 10.0
SCHEMATIC_ORIGIN_Y = 10.0
SCHEMATIC_SCALE_X = 1.90
SCHEMATIC_SCALE_Y = 1.80


def layout_x(value: float) -> float:
    return grid(SCHEMATIC_ORIGIN_X + (value - SCHEMATIC_ORIGIN_X) * SCHEMATIC_SCALE_X)


def layout_y(value: float) -> float:
    return grid(SCHEMATIC_ORIGIN_Y + (value - SCHEMATIC_ORIGIN_Y) * SCHEMATIC_SCALE_Y)


def add(
    ref: str,
    lib: str,
    value: str,
    x: float,
    y: float,
    nets: list[str | None],
    *,
    footprint: str = "",
    manufacturer: str = "",
    mpn: str = "",
    lcsc: str = "",
    assembly: str = "SMT",
    dnp: bool = False,
    note: str = "",
) -> None:
    definition = DEFS[lib]
    if len(nets) != len(definition.pins):
        raise ValueError(f"{ref}: expected {len(definition.pins)} nets, got {len(nets)}")
    COMPONENTS.append(
        Component(
            ref,
            lib,
            value,
            layout_x(x),
            layout_y(y),
            {pin.number: net for pin, net in zip(definition.pins, nets)},
            footprint,
            manufacturer,
            mpn,
            lcsc,
            assembly,
            dnp,
            note,
        )
    )


def note(text: str, x: float, y: float, size: float = 1.27) -> None:
    NOTES.append((text, layout_x(x), layout_y(y), size))


FP_SO8 = "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"
FP_SO14 = "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm"
FP_SO28 = "Package_SO:SOIC-28W_7.5x17.9mm_P1.27mm"
FP_0603 = "Resistor_SMD:R_0603_1608Metric"
FP_C0603 = "Capacitor_SMD:C_0603_1608Metric"
FP_0805 = "Resistor_SMD:R_0805_2012Metric"
FP_C0805 = "Capacitor_SMD:C_0805_2012Metric"
FP_1206 = "Resistor_SMD:R_1206_3216Metric"
FP_C1206 = "Capacitor_SMD:C_1206_3216Metric"
FP_SOT23 = "Package_TO_SOT_SMD:SOT-23"
FP_D2PAK_DIODE = "Package_TO_SOT_SMD:TO-263-2_TabPin1"
FP_CSD18540 = "INA_CUSTOM:VSON-CLIP-8_L5.0-W6.0-P1.27-BL"
FP_LM74610 = "INA_CUSTOM:VSSOP-8_L3.0-W3.0-P0.65-LS5.0-BL"
FP_TPD1E10 = "INA_CUSTOM:X1SON-2_L1.0-W0.6-P0.65-BI-1"
FP_ATO_HOLDER = "INA_CUSTOM:178.6165.0001"
FP_PC5_2 = "INA_CUSTOM:Phoenix_PC5_2_G_7_62_1720466"
FP_MSTBA_4 = "INA_CUSTOM:Phoenix_MSTBA_2_5_4_G_5_08_1757268"
FP_MSTBA_3 = "INA_CUSTOM:Phoenix_MSTBA_2_5_3_G_5_08_1757255"
FP_MSTBA_2 = "INA_CUSTOM:Phoenix_MSTBA_2_5_2_G_5_08_1757242"

P_C100N = {
    "manufacturer": "Samsung Electro-Mechanics",
    "mpn": "CL10B104KB8NNNC",
    "lcsc": "C1591",
}
P_C2U2 = {
    "manufacturer": "Samsung Electro-Mechanics",
    "mpn": "CL21B225KOFNNNE",
    "lcsc": "C28234",
}
P_R150K = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF1503T5E", "lcsc": "C22807"}
P_R27K = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF2702T5E", "lcsc": "C22967"}
P_R47K = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF4702T5E", "lcsc": "C25819"}
P_R10K = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF1002T5E", "lcsc": "C25804"}
P_R4K7 = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF4701T5E", "lcsc": "C23162"}
P_R1K = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF1001T5E", "lcsc": "C21190"}
P_R680 = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF6800T5E", "lcsc": "C23228"}
P_R120_0805 = {"manufacturer": "UNI-ROYAL", "mpn": "0805W8F1200T5E", "lcsc": "C17437"}
P_R22 = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF220JT5E", "lcsc": "C23345"}
P_R10 = {"manufacturer": "UNI-ROYAL", "mpn": "0603WAF100JT5E", "lcsc": "C22859"}


# Power input and logic rails.
note("POWER INPUT / 20 A SHARED PATH", 15, 15, 1.8)
note("Normal: one 12 V output. Absolute limit: two outputs (<200 W total).", 15, 20)
add(
    "J1",
    "CONN2",
    "PC 5/2-G-7.62 POWER INPUT",
    22,
    34,
    ["LOAD_POS", "GND"],
    footprint=FP_PC5_2,
    manufacturer="Phoenix Contact",
    mpn="1720466",
    assembly="THT/wave",
    note="32 A nominal; Phoenix drilling pattern has 3 solder pins per potential",
)
add(
    "F1",
    "FUSE",
    "ATO HOLDER + 20A FUSE",
    45,
    31,
    ["LOAD_POS", "VIN_FUSED"],
    footprint=FP_ATO_HOLDER,
    manufacturer="Littelfuse",
    mpn="178.6165.0001 + 0287020.H",
    lcsc="C207060",
    assembly="THT/manual",
    note="20 A initial; coordinate with measured inrush, wire, and battery fuse",
)
add(
    "Q1",
    "NMOS",
    "CSD18540Q5B 60V",
    68,
    28,
    ["RPOL_GATE", "12V_ACT", "VIN_FUSED"],
    footprint=FP_CSD18540,
    manufacturer="Texas Instruments",
    mpn="CSD18540Q5B",
    lcsc="C86513",
    note="TI Q5B manufacturer land pattern; physical pins 1-3=S, 4=G, 5-8=D",
)
add(
    "U13",
    "IDEAL_DIODE_CTRL",
    "LM74610QDGKRQ1",
    68,
    40,
    ["RPOL_VCAPL", "RPOL_GATE", None, "VIN_FUSED", None, "RPOL_GATE", "RPOL_VCAPH", "12V_ACT"],
    footprint=FP_LM74610,
    manufacturer="Texas Instruments",
    mpn="LM74610QDGKRQ1",
    lcsc="C2649431",
    note="TI DGK 8-pin VSSOP 3x5 mm manufacturer land pattern",
)
add(
    "C6",
    "C",
    "2.2u 16V X7R",
    48,
    40,
    ["RPOL_VCAPH", "RPOL_VCAPL"],
    footprint=FP_C0805,
    note="LM74610-Q1 charge-pump capacitor",
    **P_C2U2,
)
add(
    "C13",
    "C",
    "100p 50V C0G",
    49,
    34,
    ["VIN_FUSED", "12V_ACT"],
    footprint=FP_C0603,
    manufacturer="Samsung Electro-Mechanics",
    mpn="CL10C101JB8NNNC",
    lcsc="C14858",
    note="LM74610-Q1 anode-cathode input filter",
)
add(
    "D1",
    "DIODE",
    "SMBJ18A",
    91,
    29,
    ["12V_ACT", "GND"],
    footprint="Diode_SMD:D_SMB",
    manufacturer="Littelfuse",
    mpn="SMBJ18A",
    lcsc="C151256",
    note="Valid only when charger LOAD remains below 16 V steady state",
)
add(
    "C1",
    "C",
    "470u 35V LOW-ESR",
    91,
    38,
    ["12V_ACT", "GND"],
    footprint="Capacitor_THT:CP_Radial_D10.0mm_P5.00mm",
    manufacturer="Nichicon",
    mpn="UHE1V471MPD",
    lcsc="C116237",
    assembly="THT/manual",
)
add(
    "U4",
    "BUCK5V",
    "AP63205WU-7 5V/2A",
    68,
    52,
    ["5V_RAW", "12V_ACT", "12V_ACT", "GND", "BUCK_SW", "BUCK_BST"],
    footprint="Package_TO_SOT_SMD:TSOT-23-6",
    manufacturer="Diodes Incorporated",
    mpn="AP63205WU-7",
    lcsc="C2071056",
)
add(
    "L1",
    "L",
    "4.7uH 4.6A",
    83,
    52,
    ["BUCK_SW", "5V_RAW"],
    footprint="Inductor_SMD:L_Bourns_SRP5030T",
    manufacturer="Bourns",
    mpn="SRP5030TA-4R7M",
    lcsc="C2047088",
)
add("C7", "C", "100n 50V X7R", 78, 45, ["BUCK_BST", "BUCK_SW"], footprint=FP_C0603, **P_C100N)
add(
    "C8",
    "C",
    "10u 50V X7R",
    57,
    58,
    ["12V_ACT", "GND"],
    footprint=FP_C1206,
    manufacturer="Samsung Electro-Mechanics",
    mpn="CL31B106KBHNNNE",
    lcsc="C89632",
)
for ref, x in (("C9", 72), ("C10", 86)):
    add(
        ref,
        "C",
        "22u 10V X7R",
        x,
        58,
        ["5V_RAW", "GND"],
        footprint=FP_C1206,
        manufacturer="Samsung Electro-Mechanics",
        mpn="CL31B226KPHNNNE",
        lcsc="C87996",
    )
add(
    "F2",
    "FUSE",
    "0.75A HOLD PTC",
    91,
    49,
    ["5V_RAW", "5V_LOGIC"],
    footprint="Fuse:Fuse_1206_3216Metric",
    manufacturer="Bourns",
    mpn="MF-NSMF075-2",
    lcsc="C89653",
)
add(
    "C2",
    "C",
    "22u 10V X7R",
    91,
    56,
    ["5V_LOGIC", "GND"],
    footprint=FP_C1206,
    manufacturer="Samsung Electro-Mechanics",
    mpn="CL31B226KPHNNNE",
    lcsc="C87996",
)
add("R1", "R", "150k 1%", 45, 66, ["12V_ACT", "BATT_DIV"], footprint=FP_0603, **P_R150K)
add("R2", "R", "27k 1%", 68, 66, ["BATT_DIV", "GND"], footprint=FP_0603, **P_R27K)
add("R3", "R", "1k 1%", 45, 73, ["BATT_DIV", "BATT_ADC"], footprint=FP_0603, **P_R1K)
add("C3", "C", "100n 50V X7R", 68, 73, ["BATT_ADC", "GND"], footprint=FP_C0603, **P_C100N)
add(
    "D3",
    "BAT54S",
    "BAT54S,215 ADC CLAMP",
    86,
    70,
    ["GND", "3V3", "BATT_ADC"],
    footprint=FP_SOT23,
    manufacturer="Nexperia",
    mpn="BAT54S,215",
    lcsc="C47546",
)


# Main controller.  The SMD footprint exposes the four XIAO underside JTAG
# pads as GPIO.
note("DIRECT GPIO CONTROLLER", 112, 15, 1.8)
add(
    "U1",
    "XIAO_ESP32C6",
    "Seeed XIAO ESP32-C6 SMD",
    130,
    58,
    [
        "BATT_ADC",
        "OUT_CMD1",
        "FLOW_PULSE",
        "MCU_MASTER_EN",
        "OUT_CMD2",
        "OUT_CMD3",
        "RS485_TX",
        "OUT_CMD4",
        "LEAK_OK",
        "OUT_CMD5",
        "ESTOP_OK",
        "RS485_RX",
        "RS485_DIR",
        "TANK_EMPTY_ACTIVE",
        "TANK_FULL_ACTIVE",
        "3V3",
        "GND",
        "5V_LOGIC",
        None,
        "GND",
        None,
        "3V3",
        None,
        "GND",
    ],
    footprint="INA_ESP32C6:XIAO_ESP32C6_SMD_24P",
    manufacturer="Seeed Studio",
    mpn="XIAO ESP32-C6",
    assembly="SMT/manual",
    note=(
        "Use Seeed official 24-pad SMD land pattern; reflow/hot-air assembly "
        "is required for underside GPIO pads"
    ),
)
add("R8", "R", "47k 1%", 112, 88, ["MCU_MASTER_EN", "GND"], footprint=FP_0603, **P_R47K)


# RS485 and generic low-current field power.
note("RS485 / GENERIC PARALLEL PORTS / NO SENSOR TYPE ASSUMPTION", 180, 15, 1.8)
add(
    "U3",
    "RS485",
    "THVD1410DR",
    200,
    36,
    ["RS485_RX", "RS485_DIR", "RS485_DIR", "RS485_TX", "GND", "RS485_A_LOCAL", "RS485_B_LOCAL", "3V3"],
    footprint=FP_SO8,
    manufacturer="Texas Instruments",
    mpn="THVD1410DR",
    lcsc="C2671345",
)
add("C5", "C", "100n 50V X7R", 178, 29, ["3V3", "GND"], footprint=FP_C0603, **P_C100N)
add("R9", "R", "47k 1%", 178, 35, ["RS485_DIR", "GND"], footprint=FP_0603, **P_R47K)
add("R10", "R", "10R 1%", 225, 32, ["RS485_A_LOCAL", "RS485_A"], footprint=FP_0603, **P_R10)
add("R11", "R", "10R 1%", 225, 39, ["RS485_B_LOCAL", "RS485_B"], footprint=FP_0603, **P_R10)
add(
    "D2",
    "SM712",
    "CDSOT23-SM712",
    246,
    35,
    ["RS485_A", "RS485_B", "GND"],
    footprint=FP_SOT23,
    manufacturer="Bourns",
    mpn="CDSOT23-SM712",
    lcsc="C404012",
)
add("R12", "R", "120R 1%", 225, 47, ["RS485_A", "TERM_NODE"], footprint=FP_0805, **P_R120_0805)
add(
    "JP1",
    "JUMPER",
    "RS485 TERM ENABLE",
    246,
    47,
    ["TERM_NODE", "RS485_B"],
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    manufacturer="Sullins",
    mpn="PRPC002SAAN-RC",
    lcsc="C3346540",
    assembly="THT/manual",
    note="Fit removable 2.54 mm shorting shunt only at bus end",
)
add("R13", "R", "680R 1% BIAS", 225, 54, ["3V3", "RS485_A"], footprint=FP_0603, dnp=True, **P_R680)
add("R14", "R", "680R 1% BIAS", 246, 54, ["RS485_B", "GND"], footprint=FP_0603, dnp=True, **P_R680)
add(
    "F3",
    "FUSE",
    "0.75A HOLD / 24V PTC",
    180,
    61,
    ["12V_ACT", "12V_FIELD"],
    footprint="Fuse:Fuse_1812_4532Metric",
    manufacturer="Bourns",
    mpn="MF-MSMF075/24-2",
    lcsc="C208467",
    note="Shared protection for generic RS485/field 12 V terminals; not software switched",
)
add(
    "C11",
    "C",
    "47u 25V LOW-ESR",
    205,
    63,
    ["12V_FIELD", "GND"],
    footprint="Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
    manufacturer="Nichicon",
    mpn="UHE1E470MDD",
    lcsc="C134230",
    assembly="THT/manual",
)
for ref, label, y, dnp in (
    ("J2", "RS485 PORT 1", 74, False),
    ("J3", "RS485 PORT 2", 86, False),
    ("J4", "RS485 PORT 3", 98, True),
):
    add(
        ref,
        "CONN4",
        label,
        248,
        y,
        ["12V_FIELD", "GND", "RS485_A", "RS485_B"],
        footprint=FP_MSTBA_4,
        manufacturer="Phoenix Contact",
        mpn="1757268",
        assembly="THT/wave",
        dnp=dnp,
        note="Mating plug 1757035",
    )


# Field input conditioning and normally-closed safety loops.
note("FIELD INPUTS / NC SAFETY LOOPS FAIL OPEN", 285, 15, 1.8)
add(
    "J5",
    "CONN3",
    "FLOW 12V/PULSE/GND",
    300,
    31,
    ["12V_FIELD", "FLOW_FIELD", "GND"],
    footprint=FP_MSTBA_3,
    manufacturer="Phoenix Contact",
    mpn="1757255",
    assembly="THT/wave",
    note="Mating plug 1757022",
)
add(
    "U12",
    "FLOW_INPUT",
    "TLV7031DBVR",
    330,
    31,
    ["FLOW_SENSE", "FLOW_REF", "GND", "FLOW_PULSE", "3V3"],
    footprint="Package_TO_SOT_SMD:SOT-23-5",
    manufacturer="Texas Instruments",
    mpn="TLV7031DBVR",
    lcsc="C2869832",
    note="Default front end: dry contact or NPN/open-collector; verify actual flow output",
)
add("R16", "R", "10k 1%", 315, 25, ["3V3", "FLOW_FIELD"], footprint=FP_0603, **P_R10K)
add(
    "D34",
    "ESD2",
    "TPD1E10B06DPYR",
    307,
    37,
    ["FLOW_FIELD", "GND"],
    footprint=FP_TPD1E10,
    manufacturer="Texas Instruments",
    mpn="TPD1E10B06DPYR",
    lcsc="C48260",
    note="Bidirectional cable-entry ESD protection; place adjacent to J5",
)
add(
    "R17",
    "R",
    "2.2k 1%",
    315,
    31,
    ["FLOW_FIELD", "FLOW_SENSE"],
    footprint=FP_0603,
    manufacturer="UNI-ROYAL",
    mpn="0603WAF2201T5E",
    lcsc="C4190",
    note="Limits residual surge current into TLV7031 while preserving pulse bandwidth",
)
add("C12", "C", "100n 50V X7R", 315, 37, ["FLOW_SENSE", "GND"], footprint=FP_C0603, **P_C100N)
add("R18", "R", "47k 1%", 344, 25, ["3V3", "FLOW_REF"], footprint=FP_0603, **P_R47K)
add("R19", "R", "47k 1%", 344, 31, ["FLOW_REF", "GND"], footprint=FP_0603, **P_R47K)
for index, (ref, label, field, raw, y) in enumerate(
    (
        ("J6", "TANK EMPTY", "EMPTY_FIELD", "EMPTY_RAW", 48),
        ("J7", "TANK FULL", "FULL_FIELD", "FULL_RAW", 62),
        ("J8", "LEAK NC", "LEAK_FIELD", "LEAK_RAW", 76),
        ("J9", "EMERGENCY STOP NC", "ESTOP_FIELD", "ESTOP_RAW", 90),
    )
):
    add(
        ref,
        "CONN2",
        label,
        300,
        y,
        [field, "GND"],
        footprint=FP_MSTBA_2,
        manufacturer="Phoenix Contact",
        mpn="1757242",
        assembly="THT/wave",
        note="Mating plug 1757019",
    )
    add(f"R{20 + index * 2}", "R", "1k 1%", 322, y - 2, [field, raw], footprint=FP_0603, **P_R1K)
    add(f"R{21 + index * 2}", "R", "10k 1%", 343, y - 2, ["3V3", raw], footprint=FP_0603, **P_R10K)
    add(f"C{20 + index}", "C", "100n 50V X7R", 322, y + 4, [raw, "GND"], footprint=FP_C0603, **P_C100N)
    add(
        f"D{30 + index}",
        "ESD2",
        "TPD1E10B06DPYR",
        343,
        y + 4,
        [field, "GND"],
        footprint=FP_TPD1E10,
        manufacturer="Texas Instruments",
        mpn="TPD1E10B06DPYR",
        lcsc="C48260",
        note="LCSC verified DPY land pattern",
    )
add(
    "U11",
    "HEX_SCHMITT",
    "SN74HC14DR",
    380,
    69,
    [
        "EMPTY_RAW",
        "TANK_EMPTY_ACTIVE",
        "FULL_RAW",
        "TANK_FULL_ACTIVE",
        "LEAK_RAW",
        "LEAK_OK",
        "GND",
        "ESTOP_OK",
        "ESTOP_RAW",
        None,
        "GND",
        None,
        "GND",
        "3V3",
    ],
    footprint=FP_SO14,
    manufacturer="Texas Instruments",
    mpn="SN74HC14DR",
    lcsc="C6820",
)
add("C24", "C", "100n 50V X7R", 365, 96, ["3V3", "GND"], footprint=FP_C0603, **P_C100N)


# Hard safety gating and gate-driver section.
note("HARD SAFETY GATING / ALL OUTPUTS DEFAULT OFF", 15, 120, 1.8)
add(
    "U5",
    "QUAD_AND",
    "SN74AHCT08DR",
    55,
    145,
    [
        "MCU_MASTER_EN",
        "LEAK_OK",
        "SAFETY_STAGE1",
        "SAFETY_STAGE1",
        "ESTOP_OK",
        "MASTER_PERMIT",
        "GND",
        "OUT_GATED1",
        "MASTER_PERMIT",
        "OUT_CMD1",
        "OUT_GATED2",
        "MASTER_PERMIT",
        "OUT_CMD2",
        "5V_LOGIC",
    ],
    footprint=FP_SO14,
    manufacturer="Texas Instruments",
    mpn="SN74AHCT08DR",
    lcsc="C7480",
)
add(
    "U6",
    "QUAD_AND",
    "SN74AHCT08DR",
    100,
    145,
    [
        "OUT_CMD3",
        "MASTER_PERMIT",
        "OUT_GATED3",
        "OUT_CMD4",
        "MASTER_PERMIT",
        "OUT_GATED4",
        "GND",
        None,
        "GND",
        "GND",
        "OUT_GATED5",
        "MASTER_PERMIT",
        "OUT_CMD5",
        "5V_LOGIC",
    ],
    footprint=FP_SO14,
    manufacturer="Texas Instruments",
    mpn="SN74AHCT08DR",
    lcsc="C7480",
)
add("C30", "C", "100n 50V X7R", 74, 124, ["5V_LOGIC", "GND"], footprint=FP_C0603, **P_C100N)
add("C31", "C", "100n 50V X7R", 119, 124, ["5V_LOGIC", "GND"], footprint=FP_C0603, **P_C100N)
for index in range(5):
    add(f"R{40 + index}", "R", "47k 1%", 137 + index * 13, 124, [f"OUT_CMD{index + 1}", "GND"], footprint=FP_0603, **P_R47K)

driver_data = (
    ("U7", "OUT_GATED1", "OUT_GATED2", "DRIVER1", "DRIVER2", 155),
    ("U8", "OUT_GATED3", "OUT_GATED4", "DRIVER3", "DRIVER4", 195),
    ("U9", "OUT_GATED5", "GND", "DRIVER5", None, 235),
)
for ref, in_a, in_b, out_a, out_b, x in driver_data:
    add(
        ref,
        "DUAL_GATE_DRIVER",
        "TC4427AEOA",
        x,
        145,
        [None, in_a, "GND", in_b, out_b, "5V_LOGIC", out_a, None],
        footprint=FP_SO8,
        manufacturer="Microchip",
        mpn="TC4427AEOA",
        lcsc="C18690",
    )
    add(
        f"C{32 + (x - 155) // 40}",
        "C",
        "100n 50V X7R",
        x,
        132,
        ["5V_LOGIC", "GND"],
        footprint=FP_C0603,
        **P_C100N,
    )
    add(
        f"C{35 + (x - 155) // 40}",
        "C",
        "2.2u 16V X7R",
        x + 7,
        132,
        ["5V_LOGIC", "GND"],
        footprint=FP_C0805,
        note="Local gate-driver charge reservoir; paired with 100 nF bypass",
        **P_C2U2,
    )

note("Physical outputs are generic. Runtime mapping enforces current FGT A/B/MIXER safety rules.", 275, 124)
note("Never start two motors simultaneously. Third active command is a fault.", 275, 129)


# Five repeated fused low-side MOSFET output stages.
note("12 V MOSFET OUTPUTS / <100 W EACH / 10 A CONTINUOUS TARGET", 15, 170, 1.8)
outputs = (
    ("MOSFET OUT 1", 1, 28),
    ("MOSFET OUT 2", 2, 105),
    ("MOSFET OUT 3", 3, 182),
    ("MOSFET OUT 4", 4, 259),
    ("MOSFET OUT 5", 5, 336),
)
for label, index, x in outputs:
    fuse_ref = f"F{9 + index}"
    q_ref = f"Q{1 + index}"
    connector_ref = f"J{9 + index}"
    fly_ref = f"D{9 + index}"
    tvs_ref = f"D{19 + index}"
    gate_r = f"R{49 + index}"
    gate_pd = f"R{54 + index}"
    add(
        fuse_ref,
        "FUSE",
        f"{label} ATO HOLDER + 10A FUSE",
        x,
        187,
        ["12V_ACT", f"OUT{index}_POS"],
        footprint=FP_ATO_HOLDER,
        manufacturer="Littelfuse",
        mpn="178.6165.0001 + 0287010.H",
        lcsc="C207060",
        assembly="THT/manual",
        note="10 A initial; lower rating permitted for measured low-current loads",
    )
    add(gate_r, "R", "22R 1%", x, 197, [f"DRIVER{index}", f"GATE{index}"], footprint=FP_0603, **P_R22)
    add(gate_pd, "R", "47k 1%", x, 204, [f"GATE{index}", "GND"], footprint=FP_0603, **P_R47K)
    add(
        q_ref,
        "NMOS",
        "CSD18540Q5B 60V",
        x,
        216,
        [f"GATE{index}", f"OUT{index}_SW", "GND"],
        footprint=FP_CSD18540,
        manufacturer="Texas Instruments",
        mpn="CSD18540Q5B",
        lcsc="C86513",
        note="TI Q5B land pattern; validate thermal rise and measured inrush",
    )
    add(
        fly_ref,
        "DIODE",
        "STPS30SM60SG-TR 60V/30A",
        x,
        228,
        [f"OUT{index}_POS", f"OUT{index}_SW"],
        footprint=FP_D2PAK_DIODE,
        manufacturer="STMicroelectronics",
        mpn="STPS30SM60SG-TR",
        lcsc="C2935135",
    )
    add(
        tvs_ref,
        "DIODE",
        "OUTPUT TVS/SNUBBER DNP",
        x,
        238,
        [f"OUT{index}_SW", "GND"],
        footprint="Diode_SMD:D_SMB",
        dnp=True,
        note="Select only after cable transient measurement",
    )
    add(
        connector_ref,
        "CONN2",
        f"{label} 12V",
        x,
        250,
        [f"OUT{index}_POS", f"OUT{index}_SW"],
        footprint=FP_PC5_2,
        manufacturer="Phoenix Contact",
        mpn="1720466",
        assembly="THT/wave",
        note="32 A header; mating plug 1718481; 3 solder pins per potential",
    )


note("REV A ENGINEERING BUILD / ORDERABLE PROTOTYPE", 15, 264, 2.2)
note("Bench validation is mandatory before field use: charger range, inrush, current, thermal rise, faults, and wet-enclosure testing.", 15, 270)
note("JLCPCB PCBA: top-side SMT preferred; connector/fuse THT assembly permitted; verify LCSC stock at release.", 15, 275)


def symbol_definition(definition: SymbolDef, *, embedded: bool = True) -> str:
    symbol_name = ("INA:" if embedded else "") + definition.name
    lines = [f'\t\t(symbol {quoted(symbol_name)}']
    lines.extend(
        [
            "\t\t\t(pin_names",
            "\t\t\t\t(offset 1.016)",
            "\t\t\t)",
            "\t\t\t(exclude_from_sim no)",
            "\t\t\t(in_bom yes)",
            "\t\t\t(on_board yes)",
            f'\t\t\t(property "Reference" {quoted(definition.prefix)}',
            f"\t\t\t\t(at 0 {-definition.height / 2 - 2.54:.3f} 0)",
            f"\t\t\t\t{effects(size=1.0)}",
            "\t\t\t)",
            f'\t\t\t(property "Value" {quoted(definition.name)}',
            f"\t\t\t\t(at 0 {definition.height / 2 + 2.54:.3f} 0)",
            f"\t\t\t\t{effects(size=1.0)}",
            "\t\t\t)",
        ]
    )
    for name, value in (
        ("Footprint", ""),
        ("Datasheet", ""),
        ("Description", "INA project-local self-contained symbol"),
        ("Manufacturer", ""),
        ("MPN", ""),
        ("LCSC", ""),
        ("Assembly", ""),
        ("Engineering Note", ""),
    ):
        lines.extend(
            [
                f"\t\t\t(property {quoted(name)} {quoted(value)}",
                "\t\t\t\t(at 0 0 0)",
                f"\t\t\t\t{effects(hidden=True)}",
                "\t\t\t)",
            ]
        )
    lines.extend(
        [
            f'\t\t\t(symbol {quoted(definition.name + "_0_1")}',
            "\t\t\t\t(rectangle",
            f"\t\t\t\t\t(start {-definition.width / 2:.3f} {-definition.height / 2:.3f})",
            f"\t\t\t\t\t(end {definition.width / 2:.3f} {definition.height / 2:.3f})",
            "\t\t\t\t\t(stroke",
            "\t\t\t\t\t\t(width 0.254)",
            "\t\t\t\t\t\t(type default)",
            "\t\t\t\t\t)",
            "\t\t\t\t\t(fill",
            "\t\t\t\t\t\t(type background)",
            "\t\t\t\t\t)",
            "\t\t\t\t)",
            "\t\t\t)",
            f'\t\t\t(symbol {quoted(definition.name + "_1_1")}',
        ]
    )
    for pin in definition.pins:
        x, y, angle = definition.positions()[pin.number]
        lines.extend(
            [
                "\t\t\t\t(pin passive line",
                f"\t\t\t\t\t(at {x:.3f} {y:.3f} {angle})",
                "\t\t\t\t\t(length 2.54)",
                f"\t\t\t\t\t(name {quoted(pin.name)}",
                f"\t\t\t\t\t\t{effects(size=0.8)}",
                "\t\t\t\t\t)",
                f"\t\t\t\t\t(number {quoted(pin.number)}",
                f"\t\t\t\t\t\t{effects(size=0.8)}",
                "\t\t\t\t\t)",
                "\t\t\t\t)",
            ]
        )
    lines.extend(["\t\t\t)", "\t\t\t(embedded_fonts no)", "\t\t)"])
    return "\n".join(lines)


def property_text(
    name: str,
    value: str,
    x: float,
    y: float,
    hidden: bool = True,
    size: float = 1.27,
) -> list[str]:
    return [
        f"\t\t(property {quoted(name)} {quoted(value)}",
        f"\t\t\t(at {x:.3f} {y:.3f} 0)",
        f"\t\t\t{effects(hidden=hidden, size=size)}",
        "\t\t)",
    ]


def component_text(component: Component, root_uuid: str) -> tuple[str, list[str], list[str]]:
    definition = DEFS[component.lib]
    comp_uuid = uid(f"component:{component.ref}")
    lines = [
        "\t(symbol",
        f"\t\t(lib_id {quoted('INA:' + component.lib)})",
        f"\t\t(at {component.x:.3f} {component.y:.3f} 0)",
        "\t\t(unit 1)",
        "\t\t(exclude_from_sim no)",
        "\t\t(in_bom yes)",
        "\t\t(on_board yes)",
        f"\t\t(dnp {'yes' if component.dnp else 'no'})",
        f"\t\t(uuid {quoted(comp_uuid)})",
    ]
    lines.extend(property_text("Reference", component.ref, component.x, component.y - definition.height / 2 - 2.54, hidden=False, size=0.9))
    lines.extend(property_text("Value", component.value, component.x, component.y + definition.height / 2 + 2.54, hidden=False, size=0.9))
    lines.extend(property_text("Footprint", component.footprint, component.x, component.y))
    lines.extend(property_text("Datasheet", "~", component.x, component.y))
    lines.extend(property_text("Description", "INA ESP32-C6 solar fertigation controller", component.x, component.y))
    lines.extend(property_text("Manufacturer", component.manufacturer, component.x, component.y))
    lines.extend(property_text("MPN", component.mpn, component.x, component.y))
    lines.extend(property_text("LCSC", component.lcsc, component.x, component.y))
    lines.extend(property_text("Assembly", component.assembly, component.x, component.y))
    lines.extend(property_text("Engineering Note", component.note, component.x, component.y))
    labels: list[str] = []
    no_connects: list[str] = []
    positions = definition.positions()
    for pin in definition.pins:
        pin_uuid = uid(f"pin:{component.ref}:{pin.number}")
        lines.extend(
            [
                f'\t\t(pin {quoted(pin.number)}',
                f"\t\t\t(uuid {quoted(pin_uuid)})",
                "\t\t)",
            ]
        )
        px, py, _ = positions[pin.number]
        abs_x = component.x + px
        # KiCad library symbols use Y-up coordinates, while schematic sheet
        # coordinates are Y-down.  Mirror the local Y value when placing the
        # net label/no-connect marker on the instantiated pin.
        abs_y = component.y - py
        net = component.nets[pin.number]
        if net is None:
            no_connects.extend(
                [
                    "\t(no_connect",
                    f"\t\t(at {abs_x:.3f} {abs_y:.3f})",
                    f"\t\t(uuid {quoted(uid(f'nc:{component.ref}:{pin.number}'))})",
                    "\t)",
                ]
            )
        else:
            justification = "right bottom" if pin.side == "L" else "left bottom"
            labels.extend(
                [
                    f"\t(label {quoted(net)}",
                    f"\t\t(at {abs_x:.3f} {abs_y:.3f} 0)",
                    f"\t\t{effects(size=0.65, justify=justification)}",
                    f"\t\t(uuid {quoted(uid(f'label:{component.ref}:{pin.number}'))})",
                    "\t)",
                ]
            )
    lines.extend(
        [
            "\t\t(instances",
            f"\t\t\t(project {quoted(STEM)}",
            f"\t\t\t\t(path {quoted('/' + root_uuid)}",
            f"\t\t\t\t\t(reference {quoted(component.ref)})",
            "\t\t\t\t\t(unit 1)",
            "\t\t\t\t)",
            "\t\t\t)",
            "\t\t)",
            "\t)",
        ]
    )
    return "\n".join(lines), labels, no_connects


def generate() -> None:
    root_uuid = uid("root")
    lines = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        f"\t(uuid {quoted(root_uuid)})",
        '\t(paper "A1")',
        "\t(title_block",
        f"\t\t(title {quoted('FGT ESP32-C6 Solar Fertigation Controller')})",
        f"\t\t(date {quoted('2026-08-01')})",
        f"\t\t(rev {quoted('REV A')})",
        f"\t\t(company {quoted('INA Technologies')})",
        f"\t\t(comment 1 {quoted('JLCPCB mixed-technology PCBA baseline')})",
        f"\t\t(comment 2 {quoted('12 V loads <100 W; one normal, two absolute maximum')})",
        f"\t\t(comment 3 {quoted('ORDERABLE PROTOTYPE - VALIDATE BEFORE FIELD USE')})",
        "\t)",
        "\t(lib_symbols",
    ]
    for definition in DEFS.values():
        lines.append(symbol_definition(definition, embedded=True))
    lines.append("\t)")

    for index, (text, x, y, size) in enumerate(NOTES):
        lines.extend(
            [
                f"\t(text {quoted(text)}",
                "\t\t(exclude_from_sim no)",
                f"\t\t(at {x:.3f} {y:.3f} 0)",
                f"\t\t{effects(size=size, justify='left bottom')}",
                f"\t\t(uuid {quoted(uid(f'note:{index}'))})",
                "\t)",
            ]
        )

    component_blocks: list[str] = []
    label_lines: list[str] = []
    no_connect_lines: list[str] = []
    for component in COMPONENTS:
        block, labels, no_connects = component_text(component, root_uuid)
        component_blocks.append(block)
        label_lines.extend(labels)
        no_connect_lines.extend(no_connects)
    lines.extend(label_lines)
    lines.extend(no_connect_lines)
    lines.extend(component_blocks)
    lines.extend(
        [
            "\t(sheet_instances",
            '\t\t(path "/"',
            '\t\t\t(page "1")',
            "\t\t)",
            "\t)",
            "\t(embedded_fonts no)",
            ")",
        ]
    )
    SCH_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    symbol_library = [
        "(kicad_symbol_lib",
        "\t(version 20251024)",
        '\t(generator "kicad_symbol_editor")',
        '\t(generator_version "10.0")',
    ]
    for definition in DEFS.values():
        for line in symbol_definition(definition, embedded=False).splitlines():
            symbol_library.append(line[1:] if line.startswith("\t") else line)
    symbol_library.append(")")
    SYM_PATH.write_text("\n".join(symbol_library) + "\n", encoding="utf-8")
    SYM_TABLE_PATH.write_text(
        '(sym_lib_table\n'
        '  (version 7)\n'
        '  (lib (name "INA")(type "KiCad")(uri "${KIPRJMOD}/INA.kicad_sym")(options "")(descr "INA local symbols"))\n'
        ')\n',
        encoding="utf-8",
    )

    FP_DIR.mkdir(exist_ok=True)
    pads: list[str] = []
    side_pad_positions = {
        1: (-8.065, -7.62),
        2: (-8.065, -5.08),
        3: (-8.065, -2.54),
        4: (-8.065, 0.00),
        5: (-8.065, 2.54),
        6: (-8.065, 5.08),
        7: (-8.065, 7.62),
        8: (8.10, 7.62),
        9: (8.10, 5.08),
        10: (8.10, 2.54),
        11: (8.10, 0.00),
        12: (8.10, -2.54),
        13: (8.10, -5.08),
        14: (8.10, -7.62),
    }
    for number, (x, y) in side_pad_positions.items():
        pads.append(
            f'\t(pad {quoted(number)} smd roundrect (at {x:.4f} {y:.4f}) '
            '(size 2.75 2) (layers "F.Cu" "F.Mask") '
            '(roundrect_rratio 0.25))'
        )

    underside_pad_positions = {
        15: (-1.2834, -8.6415),
        16: (1.2566, -8.6415),
        17: (-1.2834, -6.1015),
        18: (1.2566, -6.1015),
        19: (-1.2834, -3.5615),
        20: (1.2566, -3.5615),
        21: (-1.2834, -1.0215),
        22: (1.1640, -1.0783),
    }
    for number, (x, y) in underside_pad_positions.items():
        pads.append(
            f'\t(pad {quoted(number)} smd circle (at {x:.4f} {y:.4f}) '
            '(size 1.7 1.7) (layers "F.Cu" "F.Mask"))'
        )
    for number, x in ((23, -1.7914), (24, 0.7486)):
        pads.append(
            f'\t(pad {quoted(number)} smd roundrect (at {x:.4f} 5.5317 270) '
            '(size 2.5 1.1) (layers "F.Cu" "F.Mask") '
            '(roundrect_rratio 0.25))'
        )
    footprint = [
        '(footprint "XIAO_ESP32C6_SMD_24P"',
        "\t(version 20260206)",
        '\t(generator "pcbnew")',
        '\t(layer "F.Cu")',
        '\t(descr "Seeed Studio XIAO ESP32-C6 official 24-pad SMD land pattern; paste apertures intentionally omitted for post-PCBA hand assembly")',
        '\t(tags "XIAO ESP32-C6 SMD 24 pad underside GPIO")',
        '\t(property "Reference" "REF**" (at 0 -12 0) (layer "F.SilkS")',
        '\t\t(effects (font (size 1 1) (thickness 0.15))))',
        '\t(property "Value" "XIAO_ESP32C6_SMD_24P" (at 0 12 0) (layer "F.Fab")',
        '\t\t(effects (font (size 1 1) (thickness 0.15))))',
        "\t(attr smd)",
        '\t(fp_rect (start -8.9 -10.5) (end 8.9 10.5)',
        '\t\t(stroke (width 0.10) (type default))',
        '\t\t(fill no)',
        '\t\t(layer "F.Fab"))',
        '\t(fp_line (start -8.9 -10.5) (end 8.9 -10.5)',
        '\t\t(stroke (width 0.25) (type default))',
        '\t\t(layer "F.SilkS"))',
        '\t(fp_line (start -8.9 10.5) (end 8.9 10.5)',
        '\t\t(stroke (width 0.25) (type default))',
        '\t\t(layer "F.SilkS"))',
        '\t(fp_rect (start -9.15 -10.75) (end 9.15 10.75)',
        '\t\t(stroke (width 0.05) (type default))',
        '\t\t(fill no)',
        '\t\t(layer "F.CrtYd"))',
        '\t(fp_text user "ANTENNA" (at 0 -9.7) (layer "F.Fab")',
        '\t\t(effects (font (size 0.8 0.8) (thickness 0.12))))',
        '\t(fp_text user "USB" (at 0 9) (layer "F.Fab")',
        '\t\t(effects (font (size 0.8 0.8) (thickness 0.12))))',
        *pads,
        ")",
    ]
    FP_PATH.write_text("\n".join(footprint) + "\n", encoding="utf-8")
    FP_TABLE_PATH.write_text(
        '(fp_lib_table\n'
        '  (version 7)\n'
        '  (lib (name "INA_ESP32C6")(type "KiCad")(uri "${KIPRJMOD}/INA_ESP32C6.pretty")(options "")(descr "INA XIAO footprints"))\n'
        '  (lib (name "INA_CUSTOM")(type "KiCad")(uri "${KIPRJMOD}/INA_CUSTOM.pretty")(options "")(descr "INA verified manufacturer and LCSC footprints"))\n'
        ')\n',
        encoding="utf-8",
    )

    project = {
        "board": {},
        "boards": [],
        "cvpcb": {},
        "erc": {},
        "libraries": {},
        "meta": {"filename": PRO_PATH.name, "version": 1},
        "net_settings": {"classes": [], "meta": {"version": 3}},
        "pcbnew": {},
        "schematic": {},
        "sheets": [],
        "text_variables": {
            "ASSEMBLY": "JLCPCB",
            "HW_REV": "REV_A",
            "STATUS": "ORDERABLE_ENGINEERING_BUILD",
        },
    }
    PRO_PATH.write_text(json.dumps(project, indent=2) + "\n", encoding="utf-8")

    print(f"generated {SCH_PATH}")
    print(f"generated {PRO_PATH}")
    print(f"generated {SYM_PATH}")
    print(f"generated {FP_PATH}")
    print(f"components {len(COMPONENTS)}")


if __name__ == "__main__":
    try:
        generate()
    except Exception as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        raise
