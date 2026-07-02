"""Tests for the per-operation RPC timeout resolution."""
import importlib.util
import os
import sys
import types
from pathlib import Path

# Reuse the standard shim set.
_HERE = Path(__file__).resolve().parent
_RS_DIR = _HERE.parent / "addon" / "FreeCADMCP" / "rpc_server"

for name in ("FreeCAD", "FreeCADGui", "ObjectsFem", "PySide"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

_fc = sys.modules["FreeCAD"]
_fc.Console = types.SimpleNamespace(
    PrintWarning=lambda *a, **k: None,
    PrintMessage=lambda *a, **k: None,
    PrintError=lambda *a, **k: None,
)
_fc.getUserAppDataDir = lambda: "/tmp"
_fc.newDocument = lambda *a, **k: None
_fc.getDocument = lambda *a, **k: None
_fc.listDocuments = lambda: {}
_fc.Document = type("Document", (), {})
_fc.DocumentObject = type("DocumentObject", (), {})
_fc.Vector = type("Vector", (), {})
_fc.Rotation = type("Rotation", (), {})
_fc.Placement = type("Placement", (), {})

sys.modules["FreeCADGui"].ActiveDocument = None
sys.modules["FreeCADGui"].Selection = types.SimpleNamespace(
    clearSelection=lambda: None, addSelection=lambda *a, **k: None
)
sys.modules["FreeCADGui"].SendMsgToActiveView = lambda *a, **k: None
sys.modules["FreeCADGui"].addCommand = lambda *a, **k: None
sys.modules["FreeCADGui"].getMainWindow = lambda: types.SimpleNamespace(
    findChildren=lambda *a, **k: []
)

sys.modules["PySide"].QtCore = types.SimpleNamespace(
    QTimer=types.SimpleNamespace(singleShot=lambda *a, **k: None),
    QEventLoop=types.SimpleNamespace(AllEvents=0),
    QThread=types.SimpleNamespace(msleep=lambda *a, **k: None),
)
sys.modules["PySide"].QtWidgets = types.SimpleNamespace(
    QApplication=type("QApplication", (), {"instance": staticmethod(lambda: None), "processEvents": lambda *a, **k: None}),
    QInputDialog=type("QInputDialog", (), {}),
    QLineEdit=type("QLineEdit", (), {"Normal": 0}),
    QMessageBox=type("QMessageBox", (), {"warning": staticmethod(lambda *a, **k: None)}),
    QAction=type("QAction", (), {}),
)

sys.modules["ObjectsFem"].makeMeshGmsh = lambda *a, **k: (None,)
sys.modules["ObjectsFem"].makeAnalysis = lambda *a, **k: None
sys.modules["ObjectsFem"].makeMaterialSolid = lambda *a, **k: None
sys.modules["ObjectsFem"].makeSolverCalculiXCcxTools = lambda *a, **k: None


def _load_rpc_server():
    pkg = types.ModuleType("_rs_pkg_to")
    pkg.__path__ = [str(_RS_DIR)]  # type: ignore[attr-defined]
    sys.modules["_rs_pkg_to"] = pkg
    for sub in ("parts_library", "serialize", "_fem_workdir", "_request_tracking"):
        spec = importlib.util.spec_from_file_location(
            f"_rs_pkg_to.{sub}", str(_RS_DIR / f"{sub}.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"_rs_pkg_to.{sub}"] = mod
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    spec = importlib.util.spec_from_file_location(
        "_rs_pkg_to.rpc_server", str(_RS_DIR / "rpc_server.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_rs_pkg_to.rpc_server"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Per-operation timeout resolution
# ---------------------------------------------------------------------------

def test_per_op_defaults_known():
    rpc_mod = _load_rpc_server()
    rpc = rpc_mod.FreeCADRPC()
    # Values from PER_OPERATION_TIMEOUTS class attribute.
    assert rpc._timeout_for("create_document") == 30.0
    assert rpc._timeout_for("create_object") == 60.0
    assert rpc._timeout_for("edit_object") == 60.0
    assert rpc._timeout_for("delete_object") == 30.0
    assert rpc._timeout_for("execute_code") == 30.0
    assert rpc._timeout_for("insert_part_from_library") == 30.0
    assert rpc._timeout_for("run_fem_analysis") == 600.0
    assert rpc._timeout_for("get_active_screenshot") == 30.0


def test_per_op_unknown_falls_back_to_class_timeout():
    rpc_mod = _load_rpc_server()
    rpc = rpc_mod.FreeCADRPC()
    assert rpc._timeout_for("totally-unknown-op") == rpc.TIMEOUT


def test_per_op_override_wins():
    rpc_mod = _load_rpc_server()
    rpc = rpc_mod.FreeCADRPC()
    # Per-call override takes priority over per-op default and over class default.
    assert rpc._timeout_for("create_document", override=5.0) == 5.0
    assert rpc._timeout_for("unknown-op", override=42.0) == 42.0


def test_per_op_invalid_override_ignored():
    rpc_mod = _load_rpc_server()
    rpc = rpc_mod.FreeCADRPC()
    # Negative or zero override falls back to per-op default.
    assert rpc._timeout_for("create_document", override=-1) == 30.0
    assert rpc._timeout_for("create_document", override=0) == 30.0
    # Non-numeric override falls back too.
    assert rpc._timeout_for("create_document", override="lots") == 30.0
    assert rpc._timeout_for("create_document", override=None) == 30.0


# ---------------------------------------------------------------------------
# Env-var overrides
# ---------------------------------------------------------------------------

def _reload_with_env(env: dict[str, str]):
    """Reload rpc_server with the given env vars set.

    NOTE: this does NOT restore the env on exit — the caller is expected
    to use a try/finally block if it cares about isolation. The previous
    version restored the env inside this function, which broke the test
    sequence because the constructor of ``FreeCADRPC`` is called *after*
    this helper returns, by which point the env had been restored.
    """
    import sys as _sys
    for k, v in env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # Drop every cached module we own so the constructor sees fresh env.
    for cached in list(_sys.modules):
        if (
            cached.startswith("_rs_pkg_to")
            or cached == "rpc_server"
            or cached == "_fem_workdir"
            or cached == "_request_tracking"
            or cached == "parts_library"
            or cached == "serialize"
        ):
            _sys.modules.pop(cached, None)
    return _load_rpc_server()


def _with_clean_env(env: dict[str, str]):
    """Context manager that sets *env* on entry and restores on exit.

    Use this for tests that need the env present both at module-load
    time AND at ``FreeCADRPC.__init__`` time.
    """
    import contextlib
    @contextlib.contextmanager
    def _ctx():
        saved = {k: os.environ.get(k) for k in env}
        try:
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            yield
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return _ctx()


def test_env_default_rpc_timeout():
    with _with_clean_env({"FREECAD_MCP_DEFAULT_RPC_TIMEOUT": "45"}):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        # The instance attribute is what __init__ sets; the class attribute
        # remains the code default.
        assert rpc.TIMEOUT == 45.0
        assert rpc._timeout_for("unknown-op") == 45.0


def test_env_invalid_default_falls_back():
    with _with_clean_env({"FREECAD_MCP_DEFAULT_RPC_TIMEOUT": "not-a-number"}):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        # Code default of 10 survives.
        assert rpc.TIMEOUT == 10.0


def test_env_per_op_timeouts_json():
    with _with_clean_env({
        "FREECAD_MCP_RPC_TIMEOUTS": '{"create_object": 120, "run_fem_analysis": 900}'
    }):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        assert rpc._timeout_for("create_object") == 120.0
        assert rpc._timeout_for("run_fem_analysis") == 900.0
        # Untouched op keeps its default.
        assert rpc._timeout_for("create_document") == 30.0


def test_env_per_op_timeouts_invalid_json_ignored():
    with _with_clean_env({"FREECAD_MCP_RPC_TIMEOUTS": "{not json"}):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        # Defaults survive.
        assert rpc._timeout_for("create_object") == 60.0


def test_env_per_op_timeouts_partial_invalid_entries_skipped():
    with _with_clean_env({
        "FREECAD_MCP_RPC_TIMEOUTS": '{"create_object": "bad", "delete_object": 5}'
    }):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        # Good entry applied; bad entry left at default.
        assert rpc._timeout_for("delete_object") == 5.0
        assert rpc._timeout_for("create_object") == 60.0


def test_env_per_op_must_be_dict():
    """A list or scalar JSON value is rejected as a whole."""
    with _with_clean_env({"FREECAD_MCP_RPC_TIMEOUTS": '[1, 2, 3]'}):
        rpc_mod = _reload_with_env({})
        rpc = rpc_mod.FreeCADRPC()
        # Nothing was overridden.
        assert rpc._timeout_for("create_object") == 60.0


if __name__ == "__main__":
    test_per_op_defaults_known()
    test_per_op_unknown_falls_back_to_class_timeout()
    test_per_op_override_wins()
    test_per_op_invalid_override_ignored()
    test_env_default_rpc_timeout()
    test_env_invalid_default_falls_back()
    test_env_per_op_timeouts_json()
    test_env_per_op_timeouts_invalid_json_ignored()
    test_env_per_op_timeouts_partial_invalid_entries_skipped()
    test_env_per_op_must_be_dict()
    print("All RPC timeout tests passed")
