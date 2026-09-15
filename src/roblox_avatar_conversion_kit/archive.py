from __future__ import annotations

import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath

ALLOWED_SUFFIXES = {".json", ".obj", ".mtl", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".webp"}
DEFAULT_MAX_FILES = 2048
DEFAULT_MAX_UNCOMPRESSED = 768 * 1024 * 1024
DEFAULT_MAX_SINGLE_FILE = 256 * 1024 * 1024


class UnsafeArchiveError(ValueError):
    pass


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or any(part in {"..", ""} for part in p.parts):
        raise UnsafeArchiveError(f"Unsafe archive path: {name!r}")
    if p.parts and ":" in p.parts[0]:
        raise UnsafeArchiveError(f"Drive-prefixed archive path: {name!r}")
    return p


def inspect_zip(path: Path) -> dict:
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        files = [i for i in zf.infolist() if not i.is_dir()]
        total = sum(i.file_size for i in files)
        return {
            "file_count": len(files),
            "uncompressed_bytes": total,
            "members": [i.filename for i in files],
        }


def safe_extract_zip(
    archive: Path,
    destination: Path,
    *,
    max_files: int = DEFAULT_MAX_FILES,
    max_uncompressed: int = DEFAULT_MAX_UNCOMPRESSED,
    max_single_file: int = DEFAULT_MAX_SINGLE_FILE,
) -> list[Path]:
    archive = Path(archive)
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(archive) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_files:
            raise UnsafeArchiveError(f"Archive contains {len(infos)} files; limit is {max_files}")
        total = sum(i.file_size for i in infos)
        if total > max_uncompressed:
            raise UnsafeArchiveError("Archive expands beyond the configured size limit")

        for info in infos:
            if info.file_size > max_single_file:
                raise UnsafeArchiveError(f"Archive member is too large: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise UnsafeArchiveError(f"Symlinks are not allowed: {info.filename}")
            rel = _safe_member_path(info.filename)
            suffix = Path(rel.name).suffix.lower()
            if suffix and suffix not in ALLOWED_SUFFIXES:
                raise UnsafeArchiveError(f"Unsupported file type in archive: {info.filename}")

            target = destination.joinpath(*rel.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            extracted.append(target)
    return extracted
