import tempfile
import unittest
import zipfile
from pathlib import Path

from roblox_avatar_conversion_kit.pmxeditor import (
    PmxEditorBridgeError,
    discover_pmxeditor,
    inspect_package,
)


class PmxEditorBridgeTests(unittest.TestCase):
    def test_discovers_x64_and_peplugin(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "PmxEditor_x64.exe").write_bytes(b"MZ")
            pe = root / "Lib" / "PEPlugin" / "PEPlugin.dll"
            pe.parent.mkdir(parents=True)
            pe.write_bytes(b"MZ")
            found = discover_pmxeditor(root)
            self.assertEqual(found.executable.name, "PmxEditor_x64.exe")
            self.assertEqual(found.peplugin, pe)

    def test_requires_peplugin_api(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "PmxEditor.exe").write_bytes(b"MZ")
            with self.assertRaises(PmxEditorBridgeError):
                discover_pmxeditor(root)

    def test_inspects_portable_layout_zip(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / "pmxeditor.zip"
            root = "PmxEditor_0254f_EN - 2.0"
            with zipfile.ZipFile(archive, "w") as zf:
                for name in (
                    "PmxEditor.exe",
                    "PmxEditor_x64.exe",
                    "Lib/PEPlugin/PEPlugin.dll",
                    "Lib/System/PmxLib.dll",
                    "_plugin/CSScript/CSScript.dll",
                ):
                    zf.writestr(f"{root}/{name}", b"test")
            info = inspect_package(archive)
            self.assertEqual(info["kind"], "zip")
            self.assertTrue(info["x64"])
            self.assertTrue(info["x86"])
            self.assertTrue(info["plugin_api"])
            self.assertTrue(info["pmx_library"])
            self.assertTrue(info["csscript"])


if __name__ == "__main__":
    unittest.main()
