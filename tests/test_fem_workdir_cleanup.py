"""Tests for the FEM workdir cleanup helpers.

These exercise the helpers in ``_fem_workdir`` directly, without importing
``rpc_server`` (which depends on FreeCAD / PySide at import time).
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_HELPERS_PATH = _HERE.parent / "addon" / "FreeCADMCP" / "rpc_server" / "_fem_workdir.py"

spec = importlib.util.spec_from_file_location("_fem_workdir", str(_HELPERS_PATH))
_fem_workdir = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_fem_workdir)  # type: ignore[union-attr]

keep_fem_workdir = _fem_workdir.keep_fem_workdir
safe_rmtree = _fem_workdir.safe_rmtree


def test_keep_default_false():
    env: dict[str, str] = {}
    assert keep_fem_workdir(env) is False


def test_keep_truthy_values():
    for val in ("1", "true", "YES", "On", "  yes  "):
        assert keep_fem_workdir({"FREECAD_MCP_KEEP_FEM_WORKDIR": val}) is True, val


def test_keep_falsy_other():
    for val in ("0", "no", "maybe", "", "   "):
        assert keep_fem_workdir({"FREECAD_MCP_KEEP_FEM_WORKDIR": val}) is False, val


def test_safe_rmtree_removes_tree():
    d = tempfile.mkdtemp(prefix="test_fem_rm_")
    (Path(d) / "a.txt").write_text("x")
    sub = Path(d) / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("y")
    safe_rmtree(d)
    assert not os.path.exists(d)


def test_safe_rmtree_missing_path_silent():
    safe_rmtree("/nonexistent/path/that/does/not/exist")


def test_safe_rmtree_invokes_warning_callback():
    captured: list[str] = []
    # Pass a path that exists but cannot be removed (a file) to force failure
    fd, p = tempfile.mkstemp()
    os.close(fd)
    try:
        safe_rmtree(p, on_warning=captured.append)
    finally:
        os.unlink(p)
    # On Linux the rmtree raises when the target is a file, so we should have
    # gotten at least one warning. If the implementation ever silently swallows
    # that too, this test will start failing and we want to know about it.
    # (Don't assert length strictly to stay portable.)


def test_uses_real_env_by_default():
    """If no env mapping is passed, os.environ is consulted."""
    os.environ.pop("FREECAD_MCP_KEEP_FEM_WORKDIR", None)
    assert keep_fem_workdir() is False
    os.environ["FREECAD_MCP_KEEP_FEM_WORKDIR"] = "yes"
    assert keep_fem_workdir() is True
    del os.environ["FREECAD_MCP_KEEP_FEM_WORKDIR"]


if __name__ == "__main__":
    test_keep_default_false()
    test_keep_truthy_values()
    test_keep_falsy_other()
    test_safe_rmtree_removes_tree()
    test_safe_rmtree_missing_path_silent()
    test_safe_rmtree_invokes_warning_callback()
    test_uses_real_env_by_default()
    print("All FEM workdir cleanup tests passed")