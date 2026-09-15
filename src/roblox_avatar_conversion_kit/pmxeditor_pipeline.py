from __future__ import annotations

from pathlib import Path
from typing import Any


def default_validation_outputs(model: Path) -> dict[str, Path]:
    """Return sidecar paths without ever replacing the converter's original PMX."""
    model = Path(model)
    stem = model.stem
    parent = model.parent
    return {
        "report": parent / f"{stem}.pmxeditor-report.json",
        "resave": parent / f"{stem}.pmxeditor.pmx",
        "screenshot": parent / f"{stem}.pmxeditor.png",
    }


def compare_pmxeditor_counts(writer_stats: dict[str, Any], editor_result: dict[str, Any]) -> dict[str, Any]:
    """Compare counts reported by our writer with PMXEditor's parsed object model.

    Missing writer keys are intentionally ignored so this helper remains compatible with
    older PMX writer result dictionaries.
    """
    mapping = {
        "vertices": "vertices",
        "materials": "materials",
        "bones": "bones",
        "gaze_morphs": "morphs",
        "rigid_bodies": "rigid_bodies",
        "physics_joints": "joints",
    }
    checked: dict[str, dict[str, int]] = {}
    mismatches: dict[str, dict[str, int]] = {}
    for writer_key, editor_key in mapping.items():
        if writer_key not in writer_stats or editor_key not in editor_result:
            continue
        expected = int(writer_stats[writer_key])
        actual = int(editor_result[editor_key])
        pair = {"expected": expected, "pmxeditor": actual}
        checked[editor_key] = pair
        if expected != actual:
            mismatches[editor_key] = pair
    return {
        "matches": not mismatches,
        "checked": checked,
        "mismatches": mismatches,
    }
