"""Roblox Avatar Conversion Kit."""

__version__ = "0.3.14"

# Keep facial reconstruction isolated from the binary PMX writer while still letting write_pmx use
# the latest face-region logic. Importing the package installs the extension once after pmx loads.
from . import pmx as _pmx
from .face_runtime import install as _install_face_runtime

_install_face_runtime(_pmx)
del _install_face_runtime
