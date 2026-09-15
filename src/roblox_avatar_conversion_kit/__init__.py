"""Roblox Avatar Conversion Kit."""

__version__ = "0.3.11"

# v0.3.11 layers the neutral animated-head mouth fix and the classic-MMD/VMD
# compatibility helpers on top of the stable v0.3.10 PMX writer.
from . import v0311_patch as _v0311_patch

_v0311_patch.apply()
