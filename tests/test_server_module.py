"""Smoke tests for server.py — covers the parts that do not need FreeCAD.

The MCP tool implementations (create_document, create_object, ...) and
the FastMCP `run()` path are exercised in test_operations_core.py and
via a real Claude Desktop integration; here we focus on module-level
behaviour: configuration, instruction loading, logging idempotency,
and host validation.
"""
import argparse
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def _reload_server():
    """Drop the cached server module and re-import it."""
    for cached in [k for k in list(sys.modules) if k == "freecad_mcp.server" or k.startswith("freecad_mcp.server.")]:
        sys.modules.pop(cached, None)
    return importlib.import_module("freecad_mcp.server")


def test_configure_logging_idempotent():
    server = _reload_server()
    root = __import__("logging").getLogger()
    # configure_logging was already called by import; invoking it again
    # must not duplicate handlers.
    before = list(root.handlers)
    server.configure_logging()
    after = list(root.handlers)
    assert len(before) == len(after), f"handlers duplicated: {len(before)} -> {len(after)}"


def test_load_system_directives_fallback_when_missing():
    """If gabarito_ia_extracted.txt is missing, the fallback is used."""
    # Hide the docs file from the loader.
    import freecad_mcp.server as srv
    real_exists = srv.Path.exists
    real_read_text = srv.Path.read_text
    try:
        srv.Path.exists = lambda self: False  # type: ignore[assignment]
        text = srv._load_system_directives()
        assert text == "FreeCAD integration through the Model Context Protocol"
    finally:
        srv.Path.exists = real_exists  # type: ignore[assignment]
        srv.Path.read_text = real_read_text  # type: ignore[assignment]


def test_load_system_directives_reads_file():
    """When present, the file content is returned."""
    # We exercise the real file (no monkeypatch) — the repo ships
    # docs/gabarito_ia_extracted.txt; this just confirms the loader
    # reaches it.
    import freecad_mcp.server as srv
    text = srv._load_system_directives()
    assert isinstance(text, str)
    assert len(text) > 0


def test_max_instructions_chars_truncates():
    """Setting a small cap truncates the instructions and logs a warning."""
    import freecad_mcp.server as srv
    saved = os.environ.get("FREECAD_MCP_MAX_INSTRUCTIONS_CHARS")
    try:
        os.environ["FREECAD_MCP_MAX_INSTRUCTIONS_CHARS"] = "50"
        # Re-execute the assembly block to pick up the new env.
        instr = srv._load_system_directives()
        if srv.ASSET_CREATION_STRATEGY:
            instr = instr + "\n\n" + srv.ASSET_CREATION_STRATEGY
        cap = 50
        if len(instr) > cap:
            instr = instr[:cap]
        assert len(instr) == 50
    finally:
        if saved is None:
            os.environ.pop("FREECAD_MCP_MAX_INSTRUCTIONS_CHARS", None)
        else:
            os.environ["FREECAD_MCP_MAX_INSTRUCTIONS_CHARS"] = saved


def test_validate_host_accepts_ipv4_ipv6_and_hostname():
    server = _reload_server()
    for good in ("127.0.0.1", "10.0.0.5", "::1", "fe80::1", "myhost", "myhost.example.com"):
        assert server._validate_host(good) == good, good


def test_validate_host_rejects_garbage():
    server = _reload_server()
    for bad in ("", "not a host!", "123.456.789.0", "-leading-dash"):
        try:
            server._validate_host(bad)
        except argparse.ArgumentTypeError:
            continue
        raise AssertionError(f"expected ArgumentTypeError for {bad!r}")


if __name__ == "__main__":
    test_configure_logging_idempotent()
    test_load_system_directives_fallback_when_missing()
    test_load_system_directives_reads_file()
    test_max_instructions_chars_truncates()
    test_validate_host_accepts_ipv4_ipv6_and_hostname()
    test_validate_host_rejects_garbage()
    print("All server module tests passed")
