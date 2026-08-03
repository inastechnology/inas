#!/usr/bin/env python3
"""Create a deterministic full-flash image from offset/path pairs."""

from __future__ import annotations

import argparse
from pathlib import Path


def parse_region(value: str) -> tuple[int, Path]:
    offset_text, separator, path_text = value.partition("=")
    if not separator:
        raise argparse.ArgumentTypeError("region must be OFFSET=PATH")
    return int(offset_text, 0), Path(path_text)


def parse_size(value: str) -> int:
    normalized = value.strip().upper()
    multipliers = {"KB": 1024, "MB": 1024 * 1024}
    for suffix, multiplier in multipliers.items():
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)].strip()
            return int(number, 0) * multiplier
    return int(normalized, 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--size",
        type=parse_size,
        help="Pad the image to the physical flash size (for example 8MB)",
    )
    parser.add_argument("--region", action="append", required=True, type=parse_region)
    args = parser.parse_args()

    regions = sorted(args.region)
    image = bytearray()
    previous_end = 0
    for offset, path in regions:
        payload = path.read_bytes()
        if offset < previous_end:
            raise ValueError(f"overlapping region at {offset:#x}: {path}")
        if len(image) < offset:
            image.extend(b"\xff" * (offset - len(image)))
        image.extend(payload)
        previous_end = offset + len(payload)

    if args.size is not None:
        if len(image) > args.size:
            raise ValueError(
                f"regions require {len(image)} bytes, exceeding flash size {args.size}"
            )
        image.extend(b"\xff" * (args.size - len(image)))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(image)
    print(f"Factory image: {args.output} ({len(image)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
