import tempfile
import unittest
import zipfile
from pathlib import Path

from roblox_avatar_conversion_kit.archive import UnsafeArchiveError, safe_extract_zip


class ArchiveTests(unittest.TestCase):
    def test_blocks_zip_slip(self):
        with tempfile.TemporaryDirectory() as td:
            z = Path(td) / "bad.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("../escape.obj", "v 0 0 0")
            with self.assertRaises(UnsafeArchiveError):
                safe_extract_zip(z, Path(td) / "out")

    def test_blocks_executable_extension(self):
        with tempfile.TemporaryDirectory() as td:
            z = Path(td) / "bad.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("avatar/run.exe", b"MZ")
            with self.assertRaises(UnsafeArchiveError):
                safe_extract_zip(z, Path(td) / "out")


if __name__ == "__main__":
    unittest.main()
