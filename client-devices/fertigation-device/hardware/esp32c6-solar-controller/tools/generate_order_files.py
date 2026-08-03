#!/usr/bin/env python3
"""Create JLCPCB SMT files and separate post-assembly purchasing lists."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "exports"
ASSEMBLY = EXPORTS / "assembly"
KICAD_POS = ASSEMBLY / "kicad-smt-top.csv"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_schematic as contract  # noqa: E402


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as output:
        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def grouped_components(components):
    groups = defaultdict(list)
    for component in components:
        key = (
            component.value,
            component.footprint,
            component.manufacturer,
            component.mpn,
            component.lcsc,
            component.assembly,
            component.note,
            component.dnp,
        )
        groups[key].append(component.ref)
    def natural_key(reference: str):
        return [
            int(part) if part.isdigit() else part
            for part in re.split(r"(\d+)", reference)
        ]

    normalized = []
    for key, references in groups.items():
        normalized.append((key, sorted(references, key=natural_key)))
    return sorted(normalized, key=lambda item: natural_key(item[1][0]))


def make_smt_bom() -> tuple[Path, set[str]]:
    components = [
        component
        for component in contract.COMPONENTS
        if component.assembly == "SMT" and not component.dnp
    ]
    missing = [
        component.ref
        for component in components
        if not component.lcsc or not component.mpn or not component.footprint
    ]
    if missing:
        raise RuntimeError(f"SMT parts missing order data: {', '.join(missing)}")

    rows = []
    expected_refs: set[str] = set()
    for key, refs in grouped_components(components):
        value, footprint, _manufacturer, _mpn, lcsc, _assembly, _note, _dnp = key
        expected_refs.update(refs)
        rows.append(
            {
                "Comment": value,
                "Designator": ",".join(refs),
                "Footprint": footprint.split(":")[-1],
                "LCSC Part #": lcsc,
            }
        )
    path = ASSEMBLY / "jlcpcb-smt-bom.csv"
    write_csv(path, ["Comment", "Designator", "Footprint", "LCSC Part #"], rows)
    write_csv(
        EXPORTS / "jlcpcb-bom.csv",
        ["Comment", "Designator", "Footprint", "LCSC Part #"],
        rows,
    )
    return path, expected_refs


def make_cpl(expected_refs: set[str]) -> Path:
    if not KICAD_POS.exists():
        raise FileNotFoundError(
            f"{KICAD_POS} is missing; export the top-side SMD position CSV first"
        )
    with KICAD_POS.open(newline="", encoding="utf-8-sig") as source:
        raw_rows = list(csv.DictReader(source))
    actual_refs = {row["Ref"] for row in raw_rows}
    if actual_refs != expected_refs:
        missing = sorted(expected_refs - actual_refs)
        unexpected = sorted(actual_refs - expected_refs)
        raise RuntimeError(
            f"CPL reference mismatch; missing={missing}, unexpected={unexpected}"
        )

    rows = [
        {
            "Designator": row["Ref"],
            "Mid X": f'{float(row["PosX"]):.4f}mm',
            "Mid Y": f'{float(row["PosY"]):.4f}mm',
            "Layer": "Top",
            "Rotation": f'{float(row["Rot"]):.2f}',
        }
        for row in raw_rows
    ]
    path = ASSEMBLY / "jlcpcb-smt-cpl.csv"
    write_csv(
        path,
        ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"],
        rows,
    )
    return path


def make_post_assembly_bom() -> Path:
    components = [
        component
        for component in contract.COMPONENTS
        if component.assembly != "SMT" and not component.dnp
    ]
    rows = []
    for key, refs in grouped_components(components):
        value, footprint, manufacturer, mpn, lcsc, assembly, note, _dnp = key
        rows.append(
            {
                "Designator": ",".join(refs),
                "Qty": str(len(refs)),
                "Comment": value,
                "Manufacturer": manufacturer,
                "MPN": mpn,
                "LCSC Part #": lcsc,
                "Assembly": assembly,
                "Footprint": footprint,
                "Engineering Note": note,
            }
        )
    path = ASSEMBLY / "post-assembly-bom.csv"
    write_csv(
        path,
        [
            "Designator",
            "Qty",
            "Comment",
            "Manufacturer",
            "MPN",
            "LCSC Part #",
            "Assembly",
            "Footprint",
            "Engineering Note",
        ],
        rows,
    )
    return path


def make_dnp_list() -> Path:
    rows = [
        {
            "Designator": component.ref,
            "Comment": component.value,
            "Footprint": component.footprint,
            "Reason": component.note or "Optional; do not populate for Rev A",
        }
        for component in contract.COMPONENTS
        if component.dnp
    ]
    path = ASSEMBLY / "dnp-list.csv"
    write_csv(path, ["Designator", "Comment", "Footprint", "Reason"], rows)
    return path


def make_procurement_bom() -> Path:
    rows = []
    for key, refs in grouped_components(contract.COMPONENTS):
        value, footprint, manufacturer, mpn, lcsc, assembly, note, dnp = key
        rows.append(
            {
                "Designator": ",".join(refs),
                "Qty": str(len(refs)),
                "Comment": value,
                "Manufacturer": manufacturer,
                "MPN": mpn,
                "LCSC Part #": lcsc,
                "Assembly": assembly,
                "Footprint": footprint,
                "Populate Rev A": "NO" if dnp else "YES",
                "Engineering Note": note,
            }
        )
    path = ASSEMBLY / "procurement-bom.csv"
    write_csv(
        path,
        [
            "Designator",
            "Qty",
            "Comment",
            "Manufacturer",
            "MPN",
            "LCSC Part #",
            "Assembly",
            "Footprint",
            "Populate Rev A",
            "Engineering Note",
        ],
        rows,
    )
    return path


def main() -> None:
    smt_bom, expected_refs = make_smt_bom()
    cpl = make_cpl(expected_refs)
    post_bom = make_post_assembly_bom()
    dnp = make_dnp_list()
    procurement = make_procurement_bom()
    summary = {
        "revision": "REV A",
        "status": "orderable engineering build",
        "smt_placements": len(expected_refs),
        "post_assembly_components": sum(
            1
            for component in contract.COMPONENTS
            if component.assembly != "SMT" and not component.dnp
        ),
        "dnp_components": sum(component.dnp for component in contract.COMPONENTS),
        "files": [
            str(path.relative_to(ROOT))
            for path in (smt_bom, cpl, post_bom, dnp, procurement)
        ],
    }
    summary_path = ASSEMBLY / "order-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
