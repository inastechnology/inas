#!/usr/bin/env python3
"""Fail release generation when reviewed pinouts or safety parts regress."""

from __future__ import annotations

import json

import generate_schematic as contract


components = {component.ref: component for component in contract.COMPONENTS}


def expect_nets(ref: str, expected: dict[str, str | None]) -> None:
    actual = components[ref].nets
    if actual != expected:
        raise AssertionError(f"{ref} pinout mismatch: expected={expected}, actual={actual}")


expect_nets(
    "D2",
    {"1": "RS485_A", "2": "RS485_B", "3": "GND"},
)
expect_nets(
    "D3",
    {"1": "GND", "2": "3V3", "3": "BATT_ADC"},
)
expect_nets(
    "U12",
    {
        "3": "FLOW_SENSE",
        "4": "FLOW_REF",
        "2": "GND",
        "1": "FLOW_PULSE",
        "5": "3V3",
    },
)
expect_nets("D34", {"1": "FLOW_FIELD", "2": "GND"})

if components["R17"].value != "2.2k 1%":
    raise AssertionError("R17 must retain the reviewed 2.2 kohm surge-current limit")

for ref in ("C35", "C36", "C37"):
    component = components[ref]
    if component.value != "2.2u 16V X7R" or set(component.nets.values()) != {
        "5V_LOGIC",
        "GND",
    }:
        raise AssertionError(f"{ref} gate-driver reservoir mismatch")

for index in range(1, 6):
    if components[f"Q{index + 1}"].mpn != "CSD18540Q5B":
        raise AssertionError(f"Q{index + 1} output MOSFET changed without DR")
    if "0287010.H" not in components[f"F{index + 9}"].mpn:
        raise AssertionError(f"F{index + 9} must use the reviewed 10 A ATOF")

if "0287020.H" not in components["F1"].mpn:
    raise AssertionError("F1 must use the reviewed 20 A ATOF")

for component in contract.COMPONENTS:
    if component.assembly == "SMT" and not component.dnp:
        if not component.mpn or not component.lcsc or not component.footprint:
            raise AssertionError(f"{component.ref} is missing SMT order data")

print(
    json.dumps(
        {
            "status": "hardware contract valid",
            "components": len(contract.COMPONENTS),
            "critical_pinouts": ["D2", "D3", "U12", "D34"],
            "output_channels": 5,
            "gate_driver_reservoirs": 3,
        },
        ensure_ascii=False,
    )
)
