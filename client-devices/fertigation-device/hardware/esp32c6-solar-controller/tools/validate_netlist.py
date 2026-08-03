#!/usr/bin/env python3
"""Compare every generated schematic pin/net with the reviewed contract."""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import generate_schematic as contract


ROOT = Path(__file__).resolve().parents[1]
NETLIST = ROOT / "exports" / "esp32c6-solar-controller.net.xml"


def normalized_net(name: str) -> str:
    return name.removeprefix("/")


def main() -> None:
    if not NETLIST.exists():
        raise FileNotFoundError(NETLIST)

    tree = ET.parse(NETLIST)
    actual: dict[tuple[str, str], str] = {}
    for net in tree.findall("./nets/net"):
        net_name = normalized_net(net.attrib["name"])
        for node in net.findall("node"):
            key = (node.attrib["ref"], node.attrib["pin"])
            if key in actual:
                raise AssertionError(f"duplicate netlist node {key}")
            actual[key] = net_name

    mismatches: list[str] = []
    compared = 0
    for component in contract.COMPONENTS:
        for pin, expected_net in component.nets.items():
            key = (component.ref, pin)
            actual_net = actual.get(key)
            if expected_net is None:
                # KiCad serializes an explicit no-connect marker as a unique
                # synthetic net named "unconnected-(REF-FUNCTION-PadN)".
                if actual_net is not None and not actual_net.startswith(
                    f"unconnected-({component.ref}-"
                ):
                    mismatches.append(
                        f"{component.ref}.{pin}: expected NC, actual {actual_net}"
                    )
                continue
            compared += 1
            if actual_net != expected_net:
                mismatches.append(
                    f"{component.ref}.{pin}: expected {expected_net}, actual {actual_net}"
                )

    contract_refs = {component.ref for component in contract.COMPONENTS}
    unexpected = sorted(
        f"{ref}.{pin}={net}"
        for (ref, pin), net in actual.items()
        if ref not in contract_refs
    )
    if unexpected:
        mismatches.extend(f"unexpected component node {item}" for item in unexpected)

    if mismatches:
        sys.stderr.write("\n".join(mismatches) + "\n")
        raise SystemExit(f"netlist contract mismatch: {len(mismatches)} item(s)")

    print(
        json.dumps(
            {
                "status": "schematic netlist matches hardware contract",
                "components": len(contract.COMPONENTS),
                "pins_compared": compared,
                "nets": len(tree.findall("./nets/net")),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
