#!/usr/bin/env python3
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BAR = (ROOT / "BarWidget.qml").read_text()
PANEL = (ROOT / "Panel.qml").read_text()
MODEL = (ROOT / "Model.js").read_text()


class BarThumbTests(unittest.TestCase):
    def test_uses_screenshot_icons_not_plain_numbers(self):
        self.assertIn("component WorkspaceThumb", BAR)
        self.assertIn("Image {", BAR)
        self.assertIn("fillMode: Image.PreserveAspectCrop", BAR)
        self.assertIn("numberLabel", BAR)
        self.assertIn("id: numberBadge", BAR)
        self.assertIn("z: 10", BAR)
        self.assertNotIn("WidgetButton", BAR)

    def test_keeps_hover_preview_and_click_to_focus(self):
        self.assertIn("setPreviewWorkspace", BAR)
        self.assertIn("focusWorkspace", BAR)
        self.assertIn("openForWorkspace", BAR)

    def test_reloads_when_a_capture_lands(self):
        self.assertIn("function noteCaptured", BAR)
        self.assertIn("previewUrlWithRev", BAR)
        self.assertIn("hostWidget.noteCaptured", PANEL)
        self.assertNotIn("previewGeneration", BAR)
        self.assertIn("wallpaperRev", BAR)

    def test_holds_last_shot_while_next_jpeg_loads(self):
        self.assertIn("id: bufA", BAR)
        self.assertIn("id: bufB", BAR)
        self.assertIn("function acceptBuffer", BAR)

    def test_focus_ring_tracks_an_explicit_focus_id(self):
        self.assertIn("property int focusId", BAR)
        self.assertIn("function refreshFocus", BAR)
        self.assertIn("root.focusId === modelData", BAR)

    def test_screenshot_thumbs_keep_a_visible_outline(self):
        self.assertIn("z: 11", BAR)
        self.assertIn("openPanelIndicatorWidth: 0", BAR)

    def test_thumbs_live_in_the_bar(self):
        self.assertIn("id: grid", BAR)
        self.assertNotIn("PanelWindow", BAR)
        self.assertNotIn("PopupWindow", BAR)

    def test_does_not_claim_the_original_plugin_id(self):
        self.assertIn('moduleName: "io.github.lateralcoders.workspace-thumbs"', BAR)
        self.assertNotIn("b0des", BAR)
        self.assertNotIn("io.github.bubblepaxi.workspace-preview", BAR)
        self.assertNotIn("io.github.bubblepaxi.workspace-preview", PANEL)


class LiveCaptureTests(unittest.TestCase):
    def test_does_not_poll_workspace_ids_on_a_timer(self):
        self.assertNotIn("interval: 2000", BAR)
        self.assertIn("onRawEvent", BAR)

    def test_model_can_cache_bust_preview_urls(self):
        self.assertIn("function previewUrlWithRev", MODEL)
        self.assertIn("function bumpEpochs", MODEL)
        self.assertIn("#e=", MODEL)

    def test_workspace_ten_keeps_a_readable_label(self):
        self.assertNotIn("id === 10 ? \"0\"", MODEL)

    def test_always_shows_ten_desktops(self):
        self.assertIn("[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]", BAR)

    def test_hover_preview_shows_workspace_number(self):
        self.assertIn("id: hoverNumber", PANEL)
        self.assertIn("selectedWorkspaceId", PANEL)

    def test_icon_mode_defaults_off_and_accepts_single(self):
        self.assertIn('setting("iconMode", "single")', BAR)
        self.assertIn("iconsForWorkspace", BAR)
        self.assertIn("iconForClass", BAR)
        self.assertIn("appIcons", BAR)

    def test_empty_desktops_follow_current_wallpaper(self):
        self.assertIn("applyWallpaperPath", BAR)
        self.assertIn("wallpaperResolved", BAR)
        self.assertIn("stamp-wallpaper", BAR)
        self.assertIn("id: wallpaperStamp", BAR)
        self.assertNotIn("readlink", BAR)
        self.assertIn("epochFor(id) > 0", BAR)

    def test_focus_uses_hyprland_ipc_not_hyprctl(self):
        self.assertIn("Hyprland.dispatch", BAR)
        self.assertNotIn("bar.run", BAR)
        self.assertNotIn("hyprctl", BAR)

    def test_capture_is_scaled_jpeg(self):
        helper = (ROOT / "preview-helper.py").read_text()
        self.assertIn("/usr/bin/python3", PANEL)
        self.assertIn('"-I"', PANEL)
        self.assertIn("clearEnvironment: true", PANEL)
        self.assertIn('"capture"', PANEL)
        self.assertNotIn(".tmp-ws-", PANEL)
        self.assertNotIn("mktemp", helper)
        self.assertNotIn("/tmp", helper)
        self.assertIn('"-o", monitor, "-"', helper)
        self.assertIn("ALLOWED_TOOLS", helper)

    def test_wallpaper_stamp_uses_safe_publish(self):
        self.assertIn("stamp-wallpaper", BAR)
        self.assertIn("/usr/bin/python3", BAR)
        self.assertIn('"-I"', BAR)
        self.assertIn("clearEnvironment: true", BAR)
        self.assertNotIn("readlink", BAR)
        self.assertNotIn("/tmp", BAR)


if __name__ == "__main__":
    unittest.main()
