"""Tests for the PNG -> JPEG/WebP transcoding helper."""
import base64
import importlib.util
import sys
import types
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_RS_DIR = _HERE.parent / "addon" / "FreeCADMCP" / "rpc_server"

# Standard shim set.
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
    pkg = types.ModuleType("_rs_pkg_tcode")
    pkg.__path__ = [str(_RS_DIR)]
    sys.modules["_rs_pkg_tcode"] = pkg
    for sub in ("parts_library", "serialize", "_fem_workdir", "_request_tracking"):
        spec = importlib.util.spec_from_file_location(
            f"_rs_pkg_tcode.{sub}", str(_RS_DIR / f"{sub}.py")
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"_rs_pkg_tcode.{sub}"] = mod
        spec.loader.exec_module(mod)
    spec = importlib.util.spec_from_file_location(
        "_rs_pkg_tcode.rpc_server", str(_RS_DIR / "rpc_server.py")
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_rs_pkg_tcode.rpc_server"] = mod
    spec.loader.exec_module(mod)
    return mod


# A 1x1 white PNG, used to exercise the transcoding path.
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xff"
    b"\xff?\x00\x05\xfe\x02\xfe\xa3z\xd1\xc0\x00\x00\x00\x00IEND\xaeB`\x82"
)


def test_transcode_returns_none_when_pillow_missing():
    """If Pillow is not importable, transcoding returns None."""
    rpc_mod = _load_rpc_server()
    # Force the Pillow import inside _transcode_screenshot to fail.
    saved_pil = sys.modules.pop("PIL", None)
    saved_pil_image = sys.modules.pop("PIL.Image", None)
    try:
        result = rpc_mod._transcode_screenshot(_TINY_PNG, "jpeg")
        # No Pillow -> None
        assert result is None
    finally:
        if saved_pil is not None:
            sys.modules["PIL"] = saved_pil
        if saved_pil_image is not None:
            sys.modules["PIL.Image"] = saved_pil_image


def test_transcode_unknown_format_returns_none():
    rpc_mod = _load_rpc_server()
    assert rpc_mod._transcode_screenshot(_TINY_PNG, "tiff") is None
    assert rpc_mod._transcode_screenshot(_TINY_PNG, "") is None


def test_transcode_png_passthrough_not_supported():
    """_transcode_screenshot only handles jpeg/jpg/webp; 'png' should return None
    (caller should use the raw PNG path)."""
    rpc_mod = _load_rpc_server()
    assert rpc_mod._transcode_screenshot(_TINY_PNG, "png") is None


def test_transcode_with_pillow_when_available():
    """If Pillow is importable, transcoding produces a valid base64 string."""
    pytest = type("pytest_marker", (), {})  # noqa
    try:
        from PIL import Image  # type: ignore  # noqa
    except Exception:
        return  # Pillow not installed — skip silently (test still passes)

    rpc_mod = _load_rpc_server()
    jpeg_b64 = rpc_mod._transcode_screenshot(_TINY_PNG, "jpeg")
    assert jpeg_b64 is not None
    decoded = base64.b64decode(jpeg_b64)
    # JPEG magic: FF D8 FF
    assert decoded[:3] == b"\xff\xd8\xff", f"unexpected magic: {decoded[:3]!r}"

    webp_b64 = rpc_mod._transcode_screenshot(_TINY_PNG, "webp")
    assert webp_b64 is not None
    decoded_webp = base64.b64decode(webp_b64)
    # WebP magic: 'RIFF' ... 'WEBP'
    assert decoded_webp[:4] == b"RIFF", f"unexpected magic: {decoded_webp[:4]!r}"
    assert decoded_webp[8:12] == b"WEBP", f"unexpected format: {decoded_webp[8:12]!r}"


if __name__ == "__main__":
    test_transcode_returns_none_when_pillow_missing()
    test_transcode_unknown_format_returns_none()
    test_transcode_passthrough_not_supported()
    test_transcode_with_pillow_when_available()
    print("All screenshot transcode tests passed")