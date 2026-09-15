import unittest
from importlib.resources import files


class PmxEditorViewTests(unittest.TestCase):
    def test_bridge_contains_standardized_visual_view(self):
        source = (
            files("roblox_avatar_conversion_kit")
            .joinpath("pmxeditor_assets", "RackPmxBridge.cs")
            .read_text(encoding="utf-8")
        )
        self.assertIn("NormalizeView", source)
        self.assertIn("Visible_Bone = false", source)
        self.assertIn("Visible_Body = false", source)
        self.assertIn("Visible_Joint = false", source)
        self.assertIn("FillMode.Solid", source)
        self.assertIn("SetCameraView", source)
        self.assertIn("RACK_PMX_NORMALIZE_VIEW", source)


if __name__ == "__main__":
    unittest.main()
