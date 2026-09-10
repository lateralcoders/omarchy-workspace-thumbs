#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PANEL = (ROOT / "Panel.qml").read_text()


def block_after(marker: str) -> str:
    idx = PANEL.find(marker)
    if idx < 0:
        raise AssertionError(f"missing {marker!r}")
    return PANEL[idx : idx + 400]


class PanelIdlePollTests(unittest.TestCase):
    def test_no_layout_poll_loop(self):
        self.assertNotIn("layoutPollTimer", PANEL)
        self.assertNotIn("pollLayout", PANEL)
        self.assertNotIn("interval: 120", PANEL)
        self.assertNotIn("liveThumbTimer", PANEL)

    def test_hover_uses_cached_file_not_python_read(self):
        self.assertNotIn("jpegReadProc", PANEL)
        self.assertIn("function shotUrl(", PANEL)


class PanelOverlayCaptureTests(unittest.TestCase):
    def test_hover_swap_does_not_recapture(self):
        fn = block_after("function showWorkspace(")
        self.assertIn("root.setShot(workspaceId)", fn)
        self.assertNotIn("captureWorkspace", fn)

    def test_capture_skips_while_overlay_is_on_screen(self):
        fn = block_after("function captureWorkspace(")
        self.assertIn("overlayOnScreen()", fn)
        self.assertIn("if (!force && root.overlayOnScreen()) return", fn)
        self.assertNotIn("if (!root.workspaceOccupied(id)) return", fn)

    def test_opening_preview_aborts_in_flight_capture(self):
        fn = block_after("onOpenedChanged:")
        self.assertIn("root.abortCapture()", fn)

    def test_closing_preview_recaptures_current_desktop(self):
        fn = block_after("onOpenedChanged:")
        self.assertIn("settleTimer.restart()", fn)

    def test_notifies_bar_icons_after_capture(self):
        fn = block_after("function markCaptured(")
        self.assertIn("hostWidget.noteCaptured", fn)


if __name__ == "__main__":
    unittest.main()
