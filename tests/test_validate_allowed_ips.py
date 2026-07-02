"""Tests for ``validate_allowed_ips`` in the RPC server.

Loaded from the rpc_server source via importlib so we do not need a full
FreeCAD environment. The function is pure and only depends on stdlib
``ipaddress``.
"""
import importlib.util
import sys
import types
from pathlib import Path

# Provide minimal shims so the rpc_server module imports.
_HERE = Path(__file__).resolve().parent
_RS_DIR = _HERE.parent / "addon" / "FreeCADMCP" / "rpc_server"

for name in ("FreeCAD", "FreeCADGui", "ObjectsFem", "PySide"):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)

sys.modules["FreeCAD"].Console = types.SimpleNamespace(
    PrintWarning=lambda *a, **k: None,
    PrintMessage=lambda *a, **k: None,
    PrintError=lambda *a, **k: None,
)
sys.modules["FreeCAD"].getUserAppDataDir = lambda: "/tmp"
sys.modules["FreeCAD"].newDocument = lambda *a, **k: None
sys.modules["FreeCAD"].getDocument = lambda *a, **k: None
sys.modules["FreeCAD"].listDocuments = lambda: {}
# Type annotations only — never constructed at runtime in the pure helpers.
sys.modules["FreeCAD"].Document = type("Document", (), {})
sys.modules["FreeCAD"].DocumentObject = type("DocumentObject", (), {})
sys.modules["FreeCAD"].Vector = type("Vector", (), {})
sys.modules["FreeCAD"].Rotation = type("Rotation", (), {})
sys.modules["FreeCAD"].Placement = type("Placement", (), {})

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

# Build a fake parent package so the relative imports inside rpc_server.py
# (`from .parts_library import …`, `from .serialize import …`, etc.) resolve.
_pkg_name = "_rpc_server_pkg_under_test"
pkg = types.ModuleType(_pkg_name)
pkg.__path__ = [str(_RS_DIR)]  # type: ignore[attr-defined]
sys.modules[_pkg_name] = pkg

for sub in ("parts_library", "serialize", "_fem_workdir"):
    spec = importlib.util.spec_from_file_location(
        f"{_pkg_name}.{sub}", str(_RS_DIR / f"{sub}.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"{_pkg_name}.{sub}"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

spec = importlib.util.spec_from_file_location(
    f"{_pkg_name}.rpc_server", str(_RS_DIR / "rpc_server.py")
)
_mod = importlib.util.module_from_spec(spec)
sys.modules[f"{_pkg_name}.rpc_server"] = _mod
spec.loader.exec_module(_mod)  # type: ignore[union-attr]
validate_allowed_ips = _mod.validate_allowed_ips


# ---- QW5: wildcard blocking ----

def test_blocks_ipv4_wildcard():
    valid, errors = validate_allowed_ips("0.0.0.0/0")
    assert valid == []
    assert any("wildcard" in e.lower() and "0.0.0.0/0" in e for e in errors)


def test_blocks_ipv6_wildcard():
    valid, errors = validate_allowed_ips("::/0")
    assert valid == []
    assert any("wildcard" in e.lower() and "::/0" in e for e in errors)


def test_blocks_wildcard_among_valid():
    valid, errors = validate_allowed_ips("127.0.0.1, 0.0.0.0/0, 192.168.1.0/24")
    assert "127.0.0.1" in valid
    assert "192.168.1.0/24" in valid
    assert any("0.0.0.0/0" in e for e in errors)


# ---- QW10: original validation behaviour ----

def test_empty_string_error():
    valid, errors = validate_allowed_ips("")
    assert valid == []
    assert errors


def test_whitespace_only_error():
    valid, errors = validate_allowed_ips("   ")
    assert valid == []
    assert errors


def test_leading_comma_error():
    valid, errors = validate_allowed_ips(",127.0.0.1")
    assert valid == []
    assert any("malformed" in e.lower() or "comma" in e.lower() for e in errors)


def test_double_comma_error():
    valid, errors = validate_allowed_ips("127.0.0.1,,192.168.1.0/24")
    assert valid == []
    assert any("malformed" in e.lower() or "comma" in e.lower() for e in errors)


def test_trailing_comma_error():
    valid, errors = validate_allowed_ips("127.0.0.1,")
    assert valid == []
    assert any("malformed" in e.lower() or "comma" in e.lower() for e in errors)


def test_valid_entries_pass():
    valid, errors = validate_allowed_ips("127.0.0.1, 10.0.0.0/8, 192.168.1.100")
    assert sorted(valid) == ["10.0.0.0/8", "127.0.0.1", "192.168.1.100"]
    assert errors == []


def test_invalid_entry_reported():
    valid, errors = validate_allowed_ips("127.0.0.1, not-an-ip, 10.0.0.0/8")
    assert "127.0.0.1" in valid
    assert "10.0.0.0/8" in valid
    assert any("not-an-ip" in e for e in errors)


def test_ipv6_valid():
    valid, errors = validate_allowed_ips("::1, fe80::/10")
    assert "::1" in valid
    assert "fe80::/10" in valid
    assert errors == []


def test_single_host_without_prefix_is_valid():
    # ipaddress treats a bare IP as a /32 (or /128) — keep that semantics.
    valid, errors = validate_allowed_ips("192.168.1.50")
    assert "192.168.1.50" in valid
    assert errors == []


if __name__ == "__main__":
    test_blocks_ipv4_wildcard()
    test_blocks_ipv6_wildcard()
    test_blocks_wildcard_among_valid()
    test_empty_string_error()
    test_whitespace_only_error()
    test_leading_comma_error()
    test_double_comma_error()
    test_trailing_comma_error()
    test_valid_entries_pass()
    test_invalid_entry_reported()
    test_ipv6_valid()
    test_single_host_without_prefix_is_valid()
    print("All validate_allowed_ips tests passed")