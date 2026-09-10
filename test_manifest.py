#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class ManifestTests(unittest.TestCase):
    def test_is_bar_widget_that_replaces_hover_preview(self):
        manifest = json.loads((ROOT / "manifest.json").read_text())
        self.assertEqual(manifest["id"], "io.github.lateralcoders.workspace-thumbs")
        self.assertEqual(manifest["author"], "Zute Predictive")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["kinds"], ["bar-widget"])
        self.assertEqual(manifest["barWidget"]["defaultSection"], "left")
        self.assertEqual(manifest["omarchy"]["clonedFrom"], "io.github.bubblepaxi.workspace-preview")
        self.assertEqual(manifest["entryPoints"]["barWidget"], "BarWidget.qml")
        self.assertNotEqual(manifest["id"], "io.github.bubblepaxi.workspace-preview")


if __name__ == "__main__":
    unittest.main()
