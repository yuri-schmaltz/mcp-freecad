"""Smoke test: every public module imports without raising.

Why this exists
---------------
A refactor that moves a symbol around can leave a stale import
hanging in a downstream file. Static analysis tools catch some of
this; running pytest on a tiny ``import`` test catches the rest at
almost zero cost.

The test deliberately imports the *public* surface (the things
``server.py`` and the addon rely on) and only asserts the symbols
exist. Behavioural checks live in dedicated test files; this one is
a tripwire for refactor regressions.
"""
import importlib
import sys
from pathlib import Path

# Add both src/ and the addon rpc_server/ to sys.path so we can import
# the security gate without spinning up FreeCAD.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP" / "rpc_server"))


def _safe_import(name: str):
    """Import a module and return it; skip (pass) on ImportError.

    A module that requires FreeCAD at import time is OK to skip \u2014
    the smoke test is about catching regressions in the *pure-Python*
    parts of the codebase.
    """
    try:
        return importlib.import_module(name)
    except (ImportError, ModuleNotFoundError) as e:
        if "FreeCAD" in str(e) or "PySide" in str(e) or "femtools" in str(e):
            import pytest
            pytest.skip(f"FreeCAD not available: {e}")
        raise


def test_import_circuit_breaker():
    mod = _safe_import("freecad_mcp.circuit_breaker")
    assert mod.CircuitBreaker is not None
    assert mod.CircuitOpenError is not None


def test_import_tool_policy():
    mod = _safe_import("freecad_mcp.tool_policy")
    assert mod.ALL_TOOL_NAMES
    assert "execute_code" in mod.ALL_TOOL_NAMES
    assert "create_object" in mod.ALL_TOOL_NAMES


def test_import_schemas():
    mod = _safe_import("freecad_mcp.schemas")
    assert mod.CreateObjectRequest is not None
    assert mod.EditObjectRequest is not None


def test_import_metrics():
    mod = _safe_import("freecad_mcp.metrics")
    assert mod.Counter is not None
    assert mod.Histogram is not None
    assert mod.Gauge is not None
    assert mod.MetricsRegistry is not None
    assert mod.format_prometheus is not None


def test_import_json_logging():
    mod = _safe_import("freecad_mcp.json_logging")
    assert mod.JsonLogFormatter is not None


def test_import_security_gate():
    mod = _safe_import("_security_gate")
    assert mod.can_start_remote_server is not None
    assert mod.format_refusal_message is not None
    assert "FREECAD_MCP_TLS_CERT" in mod.REQUIRED_VARS


def test_import_guidelines():
    mod = _safe_import("freecad_mcp.guidelines")
    assert mod.check_code_conflict is not None
    assert mod.check_prompt_conflict is not None
    assert mod.check_path_conflict is not None
    assert mod.scan_dangerous_tokens is not None


def test_import_responses():
    mod = _safe_import("freecad_mcp.responses")
    assert mod.text_response is not None
    assert mod.json_response is not None
    assert mod.add_screenshot_if_available is not None


def test_import_utils():
    mod = _safe_import("freecad_mcp.utils")
    assert mod.safe_operation is not None


def test_import_server_state():
    mod = _safe_import("freecad_mcp.server_state")
    assert mod.ServerState is not None
    state = mod.ServerState()
    assert state.metrics is not None  # v0.4.0 \u2014 default MetricsRegistry


def test_import_operations():
    mod = _safe_import("freecad_mcp.operations")
    # Every operation function is exported and importable.
    for name in (
        "create_document_operation", "create_object_operation", "edit_object_operation",
        "delete_object_operation", "execute_code_operation", "get_view_operation",
        "get_active_view_operation", "insert_part_from_library_operation",
        "get_objects_operation", "get_object_operation", "get_parts_list_operation",
        "list_documents_operation", "run_fem_analysis_operation", "undo_operation",
        "redo_operation", "save_document_operation", "export_object_operation",
        "health_check_operation",
    ):
        assert hasattr(mod, name), f"missing operation: {name}"


def test_import_fem_workdir():
    """The FEM workdir helpers are in the addon; ensure they import."""
    mod = _safe_import("_fem_workdir")
    assert mod.keep_fem_workdir is not None
    assert mod.safe_rmtree is not None


def test_import_request_tracking():
    mod = _safe_import("_request_tracking")
    assert mod.RequestTracker is not None
    assert mod.get_default_tracker is not None


if __name__ == "__main__":
    print("Run with pytest; direct invocation is not supported.")
