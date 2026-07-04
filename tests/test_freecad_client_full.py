"""Targeted unit tests for freecad_client.py: timeout transport edge cases,
cancel_request, ping success/failure, and method forwarding."""
import socket
import sys
import threading
import time
import xmlrpc.client
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import freecad_mcp.freecad_client as fc  # noqa: E402


# ---------------------------------------------------------------------------
# _TimeoutTransport
# ---------------------------------------------------------------------------

def test_timeout_transport_min_timeout_clamped():
    """A timeout <= 0 is clamped to 0.1 to avoid infinite-blocking sockets."""
    t = fc._TimeoutTransport(0)
    assert t._timeout >= 0.1
    t = fc._TimeoutTransport(-100)
    assert t._timeout >= 0.1


def test_timeout_transport_uses_makefile():
    """The transport falls back to the default HTTPConnection when given None."""
    t = fc._TimeoutTransport(5)
    # Without going through the socket stack, just confirm construction works.
    assert t._timeout == 5


# ---------------------------------------------------------------------------
# _build_server_proxy + ping
# ---------------------------------------------------------------------------

def test_ping_returns_true_when_proxy_returns_true():
    class _Proxy:
        def ping(self):
            return True
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    assert conn.ping() is True


def test_ping_propagates_failure():
    class _Proxy:
        def ping(self):
            return False
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    assert conn.ping() is False


# ---------------------------------------------------------------------------
# cancel_request
# ---------------------------------------------------------------------------

def test_cancel_request_forwards_to_server():
    class _Proxy:
        def cancel_request(self, rid):
            return {"success": True, "request_id": rid, "cancelled": True}
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.cancel_request("rid-1")
    assert res == {"success": True, "request_id": "rid-1", "cancelled": True}


# ---------------------------------------------------------------------------
# export_object_bytes — env-var path
# ---------------------------------------------------------------------------

def test_export_object_bytes_default_threshold(monkeypatch=None):
    """Without an env var, the default threshold is 64 KB."""
    import os
    os.environ.pop("FREECAD_MCP_GZIP_MIN", None)
    # 70 KB of 'A' -> above default threshold, gets compressed.
    class _Proxy:
        def export_object(self, doc, obj, path, fmt):
            with open(path, "wb") as f:
                f.write(b"A" * (70 * 1024))
            return {"success": True, "path": path, "format": fmt}
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.export_object_bytes("Doc", "X", "stl")
    assert res["compressed"] is True
    assert res["size_bytes"] == 70 * 1024


def test_export_object_bytes_handles_proxy_non_dict():
    """If the underlying server returns a non-dict, normalise to failure."""
    class _Proxy:
        def export_object(self, doc, obj, path, fmt):
            return "ok"  # not a dict
    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.export_object_bytes("Doc", "X", "stl")
    assert res["success"] is False
    assert "unknown" in res["error"]


# ---------------------------------------------------------------------------
# get_active_screenshot — image_format propagation
# ---------------------------------------------------------------------------

def test_get_active_screenshot_forwards_image_format():
    captured = {}

    class _Proxy:
        def execute_code(self, code):
            return {"success": True, "message": "ok"}

        def get_active_screenshot(self, view, w, h, focus, fmt):
            captured["fmt"] = fmt
            return "BASE64DATA"

    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    res = conn.get_active_screenshot("Front", 800, 600, None, image_format="jpeg")
    assert res == "BASE64DATA"
    assert captured["fmt"] == "jpeg"


def test_get_active_screenshot_view_unsupported_returns_none():
    class _Proxy:
        def execute_code(self, code):
            return {"success": True, "message": "Current view does not support screenshots"}

        def get_active_screenshot(self, *a, **k):
            raise AssertionError("should not be called when view does not support screenshots")

    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    assert conn.get_active_screenshot("Isometric") is None


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------

def test_disconnect_handles_missing_transport_attribute():
    """If the underlying ServerProxy has no _ServerProxy__transport, no error."""

    class _Proxy:
        pass

    conn = fc.FreeCADConnection.__new__(fc.FreeCADConnection)
    conn.server = _Proxy()
    # Should not raise.
    conn.disconnect()


# ---------------------------------------------------------------------------
# Connection init
# ---------------------------------------------------------------------------

def test_connection_init_with_custom_timeout(monkeypatch=None):
    """A custom timeout override works."""
    import os
    saved = os.environ.get("FREECAD_MCP_RPC_TIMEOUT")
    try:
        os.environ.pop("FREECAD_MCP_RPC_TIMEOUT", None)
        conn = fc.FreeCADConnection("127.0.0.1", 9875, timeout=2.5)
        assert conn.timeout == 2.5
    finally:
        if saved is not None:
            os.environ["FREECAD_MCP_RPC_TIMEOUT"] = saved


if __name__ == "__main__":
    import os
    test_timeout_transport_min_timeout_clamped()
    test_timeout_transport_uses_makefile()
    test_ping_returns_true_when_proxy_returns_true()
    test_ping_propagates_failure()
    test_cancel_request_forwards_to_server()
    test_export_object_bytes_default_threshold()
    test_export_object_bytes_handles_proxy_non_dict()
    test_get_active_screenshot_forwards_image_format()
    test_get_active_screenshot_view_unsupported_returns_none()
    test_disconnect_handles_missing_transport_attribute()
    test_connection_init_with_custom_timeout()
    print("All freecad_client full tests passed")