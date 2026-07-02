"""Tests for the export_object_bytes helper (gzip compression for large payloads)."""
import base64
import gzip
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import freecad_mcp.freecad_client as fc  # noqa: E402


def _build_server_proxy_mock():
    """Return a tiny ServerProxy stand-in that records calls and serves
    the bytes written to the temp file.
    """
    class _Proxy:
        def __init__(self):
            self.calls = []
            self._next_response = {}

        def export_object(self, doc_name, obj_name, path, fmt):
            self.calls.append(("export_object", doc_name, obj_name, path, fmt))
            with open(path, "wb") as f:
                f.write(b"x" * 200_000)  # 200 KB
            return {"success": True, "path": path, "format": fmt}

    return _Proxy()


def test_export_object_bytes_compresses_when_above_threshold(monkeypatch=None):
    os.environ["FREECAD_MCP_GZIP_MIN"] = "1000"  # compress anything >= 1 KB
    proxy = _build_server_proxy_mock()
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = proxy
    res = conn.export_object_bytes("Doc", "Box", "stl")
    assert res["success"]
    assert res["compressed"] is True
    assert res["size_bytes"] == 200_000
    decoded = gzip.decompress(base64.b64decode(res["b64_data"]))
    assert decoded == b"x" * 200_000
    del os.environ["FREECAD_MCP_GZIP_MIN"]


def test_export_object_bytes_raw_when_below_threshold():
    os.environ["FREECAD_MCP_GZIP_MIN"] = str(1024 * 1024)  # 1 MB
    proxy = _build_server_proxy_mock()
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = proxy
    res = conn.export_object_bytes("Doc", "Box", "stl")
    assert res["success"]
    assert res["compressed"] is False
    decoded = base64.b64decode(res["b64_data"])
    assert decoded == b"x" * 200_000
    del os.environ["FREECAD_MCP_GZIP_MIN"]


def test_export_object_bytes_propagates_failure():
    os.environ.pop("FREECAD_MCP_GZIP_MIN", None)

    class _Proxy:
        def export_object(self, doc_name, obj_name, path, fmt):
            return {"success": False, "error": "no such object"}

    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.export_object_bytes("Doc", "Missing", "stl")
    assert res["success"] is False
    assert "no such object" in res["error"]


def test_export_object_bytes_actually_compresses_well():
    """Highly compressible input (all zeros) should shrink dramatically."""
    os.environ["FREECAD_MCP_GZIP_MIN"] = "100"

    class _Proxy:
        def export_object(self, doc_name, obj_name, path, fmt):
            with open(path, "wb") as f:
                f.write(b"\x00" * 100_000)  # 100 KB of zeros
            return {"success": True, "path": path, "format": fmt}

    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.export_object_bytes("Doc", "Box", "stl")
    assert res["success"]
    assert res["compressed"] is True
    # Gzipped zeros: ~100 bytes vs 100KB original.
    wire_size = len(res["b64_data"])
    assert wire_size < 200, f"compression ineffective: {wire_size} bytes"
    decoded = gzip.decompress(base64.b64decode(res["b64_data"]))
    assert decoded == b"\x00" * 100_000
    del os.environ["FREECAD_MCP_GZIP_MIN"]


if __name__ == "__main__":
    test_export_object_bytes_compresses_when_above_threshold()
    test_export_object_bytes_raw_when_below_threshold()
    test_export_object_bytes_propagates_failure()
    test_export_object_bytes_actually_compresses_well()
    print("All export compression tests passed")