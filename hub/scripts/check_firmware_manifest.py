#!/usr/bin/env python3
import sys
from pathlib import Path


def _main() -> int:
    hub_src = Path(__file__).resolve().parents[1] / "src"
    if str(hub_src) not in sys.path:
        sys.path.insert(0, str(hub_src))

    from ina_device_hub.firmware_format_checker import main

    return main()


if __name__ == "__main__":
    raise SystemExit(_main())
