"""Security gate for the remote-connections toggle.

Pure functions that decide whether the RPC server may start with a
non-loopback bind address. Extracted from ``rpc_server`` so unit
tests can exercise the policy without spinning up FreeCAD / Qt.

The contract:

* If the bind host is ``localhost`` (or ``::1``), the gate is open \u2014
  no TLS/auth required.
* Otherwise, the gate requires:
    1. ``FREECAD_MCP_TLS_CERT`` \u2014 path to a PEM certificate.
    2. ``FREECAD_MCP_TLS_KEY`` \u2014 path to a PEM private key.
    3. ``FREECAD_MCP_AUTH_TOKEN`` \u2014 a non-empty shared secret.
  Without all three, the server refuses to start and reports which
  variables are missing. The same gate runs in
  ``ToggleRemoteConnectionsCommand.Activated`` to give the user a
  clear dialog before they can save a dangerous setting.
"""
from __future__ import annotations

import os
from typing import Iterable

LOCALHOST_NAMES: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})

REQUIRED_VARS: tuple[str, ...] = (
    "FREECAD_MCP_TLS_CERT",
    "FREECAD_MCP_TLS_KEY",
    "FREECAD_MCP_AUTH_TOKEN",
)


def _env_lookup(env: dict[str, str] | None) -> dict[str, str]:
    """Read from the provided env mapping (defaults to ``os.environ``).

    Splitting the lookup lets tests pass a controlled dict without
    monkey-patching the process environment.
    """
    return os.environ if env is None else env


def is_local_bind(host: str) -> bool:
    """Return True if *host* is a loopback address/name."""
    return host in LOCALHOST_NAMES


def missing_security_env_vars(env: dict[str, str] | None = None) -> list[str]:
    """Return the list of required env vars that are unset/empty.

    The caller can decide what to do with the list (refuse to start,
    show a dialog, etc.).
    """
    lookup = _env_lookup(env)
    return [name for name in REQUIRED_VARS if not (lookup.get(name, "").strip())]


def can_start_remote_server(
    host: str,
    env: dict[str, str] | None = None,
) -> tuple[bool, list[str]]:
    """Decide whether the RPC server may bind to *host*.

    Returns ``(allowed, missing_vars)``. ``missing_vars`` is empty when
    the call is allowed. When ``host`` is a loopback address the gate
    is open and ``missing_vars`` is always empty.
    """
    if is_local_bind(host):
        return True, []
    missing = missing_security_env_vars(env)
    return (not missing), missing


def format_refusal_message(missing: Iterable[str]) -> str:
    """Human-readable refusal for logs and dialogs."""
    missing_list = list(missing)
    if not missing_list:
        return ""
    return (
        f"Refusing to start: remote_enabled requires {', '.join(missing_list)}. "
        "Set them in the FreeCAD process environment and try again. "
        "See SECURITY.md for the threat model."
    )


__all__ = [
    "LOCALHOST_NAMES",
    "REQUIRED_VARS",
    "is_local_bind",
    "missing_security_env_vars",
    "can_start_remote_server",
    "format_refusal_message",
]
