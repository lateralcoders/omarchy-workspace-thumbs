#!/usr/bin/env python3
import unittest
from pathlib import Path

MODEL = (Path(__file__).resolve().parent / "Model.js").read_text()


class IconModeModelTests(unittest.TestCase):
    def test_skips_hidden_and_unmapped(self):
        self.assertIn("ipc.mapped === false", MODEL)
        self.assertIn("ipc.hidden === true", MODEL)
        self.assertIn("ipc.minimized === true", MODEL)

    def test_single_picks_largest_area(self):
        self.assertIn('mode === "single"', MODEL)
        self.assertIn("rows[j].area > best.area", MODEL)

    def test_all_caps_unique_classes(self):
        self.assertIn("maxIcons", MODEL)
        self.assertIn("seen[key]", MODEL)

    def test_icon_names_include_class_aliases(self):
        self.assertIn("visual-studio-code", MODEL)
        self.assertIn("function cachedIcon", MODEL)


if __name__ == "__main__":
    unittest.main()
