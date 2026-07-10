"""Settings persistence for the FreeCAD MCP addon.

Extracted from ``rpc_server`` so unit tests can exercise the
load/save/fallback logic without spinning up FreeCAD. The settings
file lives at one of three locations (FreeCAD user dir → XDG / HOME
config → temp), depending on which is writable on the host.

The module is deliberately a thin wrapper around ``json`` so we can
surgically replace the storage backend (e.g. keyring) without
touching the call sites.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

try:
    import FreeCAD
except Exception:
    # Module is loaded outside FreeCAD during unit tests. Provide a
    # placeholder so the imports below don't blow up.
    FreeCAD = None  # type: ignore[assignment]


_SETTINGS_FILENAME = "freecad_mcp_settings.json"

_DEFAULT_SETTINGS: dict[str, Any] = {
    "remote_enabled": False,
    "allowed_ips": "127.0.0.1",
    "auto_start_rpc": False,
}


def _writable_dir(path: str) -> bool:
    """Return True if *path* exists and is writable by the current user."""
    if not path:
        return False
    if not os.path.isdir(path):
        return False
    # Probe with a touch-then-remove of a temp filename.
    try:
        fd, probe = tempfile.mkstemp(prefix=".mcp_write_probe_", dir=path)
        os.close(fd)
        os.unlink(probe)
        return True
    except (OSError, PermissionError):
        return False


def _ensure_dir(path: str) -> bool:
    """Create *path* (and parents) if it doesn't exist. Returns True on success."""
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except (OSError, PermissionError):
        return False


def _resolve_settings_dir() -> str:
    """Pick a directory that exists and is writable for the settings file.

    Tries in order:

    1. ``FreeCAD.getUserAppDataDir()`` — the canonical FreeCAD user dir.
       If it exists but is read-only (sandboxed installs, portable mode on
       Windows, CI), we fall back.
    2. ``$XDG_CONFIG_HOME/freecad-mcp`` (Linux) or ``$HOME/.config/freecad-mcp``.
    3. ``tempfile.gettempdir()/freecad-mcp`` as a last resort.

    Returns the first directory that exists and is writable, or the temp
    fallback even if not writable (so the caller at least has a path to
    report; ``save_settings`` will still surface the I/O error).
    """
    # 1. FreeCAD user data dir.
    primary: str | None = None
    if FreeCAD is not None:
        try:
            primary = FreeCAD.getUserAppDataDir()
        except Exception as e:
            if hasattr(FreeCAD, "Console"):
                FreeCAD.Console.PrintWarning(
                    f"MCP settings: FreeCAD.getUserAppDataDir() raised {type(e).__name__}: {e}\n"
                )
            primary = None
    if primary and _ensure_dir(primary) and _writable_dir(primary):
        return primary

    if primary and hasattr(FreeCAD, "Console"):
        FreeCAD.Console.PrintWarning(
            f"MCP settings: {primary!r} is not writable; falling back.\n"
        )

    # 2. XDG / HOME config.
    xdg = os.environ.get("XDG_CONFIG_HOME", "").strip()
    candidates: list[str] = []
    if xdg:
        candidates.append(os.path.join(xdg, "freecad-mcp"))
    home = os.environ.get("HOME", "").strip()
    if home:
        candidates.append(os.path.join(home, ".config", "freecad-mcp"))
        candidates.append(os.path.join(home, "freecad-mcp"))

    for c in candidates:
        if _ensure_dir(c) and _writable_dir(c):
            return c

    # 3. Temp fallback (last resort).
    fallback = os.path.join(tempfile.gettempdir(), "freecad-mcp")
    _ensure_dir(fallback)
    return fallback


def _get_settings_path() -> str:
    """Return the absolute path to the settings JSON file.

    Resolved lazily on each call so a deployment that gains write access
    mid-session (e.g. user fixes a permission) starts using the proper
    location without a restart.
    """
    return os.path.join(_resolve_settings_dir(), _SETTINGS_FILENAME)


def load_settings() -> dict[str, Any]:
    """Read the persisted settings, falling back to defaults.

    A missing or unreadable file yields the defaults; a partial file is
    back-filled with the missing keys.
    """
    path = _get_settings_path()
    if os.path.exists(path):
        try:
            with open(path) as f:
                settings = json.load(f)
            # Ensure all default keys exist
            for key, value in _DEFAULT_SETTINGS.items():
                if key not in settings:
                    settings[key] = value
            return settings
        except Exception as e:
            if FreeCAD is not None and hasattr(FreeCAD, "Console"):
                FreeCAD.Console.PrintWarning(f"Failed to load MCP settings from {path}: {e}\n")
    return dict(_DEFAULT_SETTINGS)


def save_settings(settings: dict[str, Any]) -> None:
    """Persist *settings* to disk; log an error on I/O failure."""
    path = _get_settings_path()
    try:
        # Make sure the directory exists (idempotent) before opening for write.
        _ensure_dir(os.path.dirname(path))
        with open(path, "w") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        if FreeCAD is not None and hasattr(FreeCAD, "Console"):
            FreeCAD.Console.PrintError(f"Failed to save MCP settings to {path}: {e}\n")


__all__ = [
    "_SETTINGS_FILENAME",
    "_DEFAULT_SETTINGS",
    "_writable_dir",
    "_ensure_dir",
    "_resolve_settings_dir",
    "_get_settings_path",
    "load_settings",
    "save_settings",
]
