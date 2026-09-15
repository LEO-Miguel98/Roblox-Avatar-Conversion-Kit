import unittest
from pathlib import Path

from roblox_avatar_conversion_kit.cli import build_parser
from roblox_avatar_conversion_kit.pmxeditor_pipeline import (
    compare_pmxeditor_counts,
    default_validation_outputs,
)


class PmxEditorPipelineTests(unittest.TestCase):
    def test_default_sidecars_do_not_replace_original(self):
        model = Path("output") / "Diane.pmx"
        outputs = default_validation_outputs(model)
        self.assertEqual(outputs["report"], Path("output/Diane.pmxeditor-report.json"))
        self.assertEqual(outputs["resave"], Path("output/Diane.pmxeditor.pmx"))
        self.assertEqual(outputs["screenshot"], Path("output/Diane.pmxeditor.png"))
        self.assertNotEqual(outputs["resave"], model)

    def test_count_comparison_detects_mismatch(self):
        writer = {
            "vertices": 100,
            "materials": 4,
            "bones": 20,
            "gaze_morphs": 4,
            "rigid_bodies": 8,
            "physics_joints": 6,
        }
        editor = {
            "vertices": 100,
            "materials": 4,
            "bones": 20,
            "morphs": 4,
            "rigid_bodies": 8,
            "joints": 5,
        }
        result = compare_pmxeditor_counts(writer, editor)
        self.assertFalse(result["matches"])
        self.assertEqual(result["mismatches"]["joints"]["expected"], 6)
        self.assertEqual(result["mismatches"]["joints"]["pmxeditor"], 5)

    def test_rack_pmx_accepts_integrated_pmxeditor_flags(self):
        args = build_parser().parse_args([
            "pmx", "Diane.zip", "-o", "Diane.pmx",
            "--pmxeditor", r"C:\\Tools\\PmxEditor",
            "--pmxeditor-close",
        ])
        self.assertEqual(args.command, "pmx")
        self.assertTrue(args.pmxeditor_close)
        self.assertFalse(args.no_pmxeditor_resave)
        self.assertFalse(args.no_pmxeditor_screenshot)


if __name__ == "__main__":
    unittest.main()
