import os
from functools import cache

import FreeCAD
import FreeCADGui


def _safe_resolve(parts_lib_path: str, relative_path: str) -> str:
    """Resolve ``relative_path`` against the parts library, refusing traversal.

    Raises ``ValueError`` if the input is empty, absolute, contains ``..``
    segments, or resolves outside the parts library root.
    """
    if not relative_path or not relative_path.strip():
        raise ValueError("relative_path must not be empty.")
    # Reject absolute paths and Windows-style drive letters early.
    if os.path.isabs(relative_path) or relative_path.startswith(("/", "\\")):
        raise ValueError(f"relative_path must be relative: {relative_path!r}")
    # Normalise and reject any path that escapes via ..
    safe = os.path.normpath(relative_path)
    if safe.startswith("..") or os.path.isabs(safe):
        raise ValueError(f"relative_path escapes parts library: {relative_path!r}")
    # Final defence: the resolved absolute path must live under the library root.
    lib_root = os.path.realpath(parts_lib_path)
    candidate = os.path.realpath(os.path.join(lib_root, safe))
    if candidate != lib_root and not candidate.startswith(lib_root + os.sep):
        raise ValueError(f"relative_path escapes parts library: {relative_path!r}")
    return candidate


def insert_part_from_library(relative_path):
    parts_lib_path = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "parts_library")
    part_path = _safe_resolve(parts_lib_path, relative_path)

    if not os.path.exists(part_path):
        raise FileNotFoundError(f"Not found: {part_path}")

    FreeCADGui.ActiveDocument.mergeProject(part_path)


@cache
def get_parts_list() -> list[str]:
    parts_lib_path = os.path.join(FreeCAD.getUserAppDataDir(), "Mod", "parts_library")

    if not os.path.exists(parts_lib_path):
        raise FileNotFoundError(f"Not found: {parts_lib_path}")

    parts = []

    for root, _, files in os.walk(parts_lib_path):
        for file in files:
            if file.endswith(".FCStd"):
                relative_path = os.path.relpath(os.path.join(root, file), parts_lib_path)
                parts.append(relative_path)

    return parts
