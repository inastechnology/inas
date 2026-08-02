from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

from shipping_tool.ui.main_window import ShippingToolWindow

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:
    TkinterDnD = None


def main() -> int:
    root: tk.Tk
    if TkinterDnD is not None:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()

    ShippingToolWindow(
        root=root,
        application_dir=Path(__file__).resolve().parents[1],
        drag_and_drop_available=TkinterDnD is not None,
    )
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
