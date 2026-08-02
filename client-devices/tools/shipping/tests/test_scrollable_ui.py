from __future__ import annotations

import unittest
from types import SimpleNamespace

from shipping_tool.ui.main_window import ShippingToolWindow


class FakeNotebook:
    def select(self) -> str:
        return "flash-tab"


class FakeCanvas:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    def yview_scroll(self, amount: int, unit: str) -> None:
        self.calls.append((amount, unit))


class ScrollableUiTest(unittest.TestCase):
    def create_window(self) -> tuple[ShippingToolWindow, FakeCanvas]:
        window = ShippingToolWindow.__new__(ShippingToolWindow)
        canvas = FakeCanvas()
        window.tabs = FakeNotebook()
        window.tab_scroll_canvases = {"flash-tab": canvas}
        return window, canvas

    def test_mouse_wheel_scrolls_active_tab_down(self) -> None:
        window, canvas = self.create_window()

        result = window.scroll_active_tab(
            SimpleNamespace(num=0, delta=-120)
        )

        self.assertEqual(result, "break")
        self.assertEqual(canvas.calls, [(3, "units")])

    def test_linux_wheel_scrolls_active_tab_up(self) -> None:
        window, canvas = self.create_window()

        result = window.scroll_active_tab(SimpleNamespace(num=4, delta=0))

        self.assertEqual(result, "break")
        self.assertEqual(canvas.calls, [(-3, "units")])


if __name__ == "__main__":
    unittest.main()
