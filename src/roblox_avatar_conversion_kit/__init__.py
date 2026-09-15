"""Roblox Avatar Conversion Kit."""

__version__ = "0.3.20"

# Keep facial reconstruction isolated from the binary PMX writer while still letting write_pmx use
# the latest face-region logic. Importing the package installs the extensions once after pmx loads.
from . import pmx as _pmx
from .face_runtime import install as _install_face_runtime
from .face_follow import install as _install_face_follow
from .face_boundary import install as _install_face_boundary

_install_face_runtime(_pmx)
_install_face_follow(_pmx)
_install_face_boundary(_pmx)
del _install_face_runtime
del _install_face_follow
del _install_face_boundary
