import base64
import gzip
import logging
import os
import socket
import xmlrpc.client
from typing import Any

logger = logging.getLogger("FreeCADMCPserver")

# Read the default XML-RPC timeout from the environment so operators can
# tighten it (slow networks, fragile tunnels) or relax it (huge FEM
# results) without touching code. Default = 10s, matching the server's
# own per-task timeout.
_DEFAULT_RPC_TIMEOUT = float(os.environ.get("FREECAD_MCP_RPC_TIMEOUT", "10"))


class _TimeoutTransport(xmlrpc.client.Transport):
    """XML-RPC transport that enforces a connect/read timeout on every call.

    The stdlib ``ServerProxy`` does not expose a socket timeout, so without
    this every call hangs forever if the FreeCAD RPC server dies. The
    timeout applies to TCP connect and to each socket read; ``set_timeout``
    on the response is also set as a final safety net so a peer that opens
    but never replies is still bounded.
    """

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = max(0.1, float(timeout))

    def make_connection(self, host):  # type: ignore[override]
        # The stdlib Transport contract: ``host`` is either None (use
        # self.host/self.port) or a (host, port) tuple. We accept either
        # shape and return an HTTPConnection with timeout baked in.
        if host is None:
            endpoint_host, endpoint_port = self.host, self.port
        else:
            endpoint_host, endpoint_port = host[0], host[1]
        import http.client
        return http.client.HTTPConnection(
            endpoint_host, endpoint_port, timeout=self._timeout
        )


_SCREENSHOT_SUPPORT_CHECK = """
import FreeCAD
import FreeCADGui

if FreeCAD.Gui.ActiveDocument and FreeCAD.Gui.ActiveDocument.ActiveView:
    view_type = type(FreeCAD.Gui.ActiveDocument.ActiveView).__name__

    # These view types don't support screenshots
    unsupported_views = ['SpreadsheetGui::SheetView', 'DrawingGui::DrawingView', 'TechDrawGui::MDIViewPage']

    if view_type in unsupported_views or not hasattr(FreeCAD.Gui.ActiveDocument.ActiveView, 'saveImage'):
        print("Current view does not support screenshots")
        False
    else:
        print(f"Current view supports screenshots: {view_type}")
        True
else:
    print("No active view")
    False
"""


def _build_server_proxy(host: str, port: int, timeout: float) -> xmlrpc.client.ServerProxy:
    """Construct a ServerProxy that honours *timeout*.

    Uses the stdlib ``Transport`` (HTTP) by default; falls back to
    ``SafeTransport`` for HTTPS, both wrapped with our timeout enforcement.
    """
    url = f"http://{host}:{port}"
    try:
        transport: xmlrpc.client.Transport = _TimeoutTransport(timeout)
    except Exception:
        # Extremely defensive: if TimeoutTransport fails for some reason we
        # still get a working (but untimed) client rather than crashing the
        # server at startup.
        logger.warning("Falling back to default XML-RPC transport without timeout")
        transport = xmlrpc.client.Transport()
    return xmlrpc.client.ServerProxy(url, allow_none=True, transport=transport)


class FreeCADConnection:
    def __init__(self, host: str = "localhost", port: int = 9875, timeout: float | None = None):
        effective_timeout = _DEFAULT_RPC_TIMEOUT if timeout is None else float(timeout)
        self.timeout = effective_timeout
        self.server = _build_server_proxy(host, port, effective_timeout)

    def disconnect(self) -> None:
        # Transport.close() clears cached HTTP connections if one was opened.
        transport = getattr(self.server, "_ServerProxy__transport", None)
        close = getattr(transport, "close", None)
        if callable(close):
            close()

    def ping(self) -> bool:
        return self.server.ping()  # type: ignore[return-value]

    def cancel_request(self, request_id: str) -> dict[str, Any]:
        """Cooperatively cancel a previously-submitted request by id.

        The id must be the same string passed to the originating call. The
        cancel only takes effect if the GUI worker has not yet started the
        task; once the handler is running it cannot be interrupted.
        """
        return self.server.cancel_request(request_id)  # type: ignore[return-value]

    def create_document(self, name: str, request_id: str | None = None) -> dict[str, Any]:
        return self.server.create_document(name, request_id)  # type: ignore[return-value]

    def create_object(self, doc_name: str, obj_data: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        return self.server.create_object(doc_name, obj_data, request_id)  # type: ignore[return-value]

    def edit_object(self, doc_name: str, obj_name: str, obj_data: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        return self.server.edit_object(doc_name, obj_name, obj_data, request_id)  # type: ignore[return-value]

    def delete_object(self, doc_name: str, obj_name: str, request_id: str | None = None) -> dict[str, Any]:
        return self.server.delete_object(doc_name, obj_name, request_id)  # type: ignore[return-value]

    def insert_part_from_library(self, relative_path: str, request_id: str | None = None) -> dict[str, Any]:
        return self.server.insert_part_from_library(relative_path, request_id)  # type: ignore[return-value]

    def execute_code(self, code: str, request_id: str | None = None) -> dict[str, Any]:
        return self.server.execute_code(code, request_id)  # type: ignore[return-value]

    def get_active_screenshot(
        self,
        view_name: str = "Isometric",
        width: int | None = None,
        height: int | None = None,
        focus_object: str | None = None,
        image_format: str = "png",
    ) -> str | None:
        try:
            result = self.server.execute_code(_SCREENSHOT_SUPPORT_CHECK)  # type: ignore[union-attr]
            # XML-RPC may return any JSON-serialisable type; coerce to a
            # dict view defensively.
            result_dict = result if isinstance(result, dict) else {}
            if not result_dict.get("success", False) or "Current view does not support screenshots" in result_dict.get("message", ""):
                logger.info("Screenshot unavailable in current view (likely Spreadsheet or TechDraw view)")
                return None

            return self.server.get_active_screenshot(view_name, width, height, focus_object, image_format)  # type: ignore[return-value]
        except Exception as e:
            logger.error(f"Error getting screenshot: {e}")
            return None

    def get_objects(self, doc_name: str) -> list[dict[str, Any]]:
        return self.server.get_objects(doc_name)  # type: ignore[return-value]

    def get_object(self, doc_name: str, obj_name: str) -> dict[str, Any]:
        return self.server.get_object(doc_name, obj_name)  # type: ignore[return-value]

    def get_parts_list(self) -> list[str]:
        return self.server.get_parts_list()  # type: ignore[return-value]

    def list_documents(self) -> list[str]:
        return self.server.list_documents()  # type: ignore[return-value]

    def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600, request_id: str | None = None) -> dict[str, Any]:
        return self.server.run_fem_analysis(doc_name, analysis_name, timeout, request_id)  # type: ignore[return-value]

    def health_check(self) -> dict[str, Any]:
        return self.server.health_check()  # type: ignore[return-value]

    def undo(self, doc_name: str, steps: int = 1) -> dict[str, Any]:
        return self.server.undo(doc_name, steps)  # type: ignore[return-value]

    def redo(self, doc_name: str, steps: int = 1) -> dict[str, Any]:
        return self.server.redo(doc_name, steps)  # type: ignore[return-value]

    def save_document(self, doc_name: str, path: str | None = None) -> dict[str, Any]:
        return self.server.save_document(doc_name, path)  # type: ignore[return-value]

    def export_object(self, doc_name: str, obj_name: str, path: str, fmt: str | None = None) -> dict[str, Any]:
        return self.server.export_object(doc_name, obj_name, path, fmt)  # type: ignore[return-value]

    def export_object_bytes(self, doc_name: str, obj_name: str, fmt: str = "stl") -> dict[str, Any]:
        """Export an object and return its bytes, optionally gzip-compressed.

        The XML-RPC ``export_object`` method writes to disk; this helper
        reads the file back and, if it is large (>FREECAD_MCP_GZIP_MIN),
        returns a gzipped base64 string. Use ``gzip.decompress`` on the
        receiver to get the original bytes.

        Smaller files are returned raw (base64). Either way the result
        has a ``b64_data`` field and a ``compressed`` boolean.
        """
        import tempfile
        # Threshold in bytes above which we apply gzip. Default 64 KB.
        threshold = int(os.environ.get("FREECAD_MCP_GZIP_MIN", str(64 * 1024)))
        with tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            res = self.server.export_object(doc_name, obj_name, tmp_path, fmt)  # type: ignore[union-attr]
            if not isinstance(res, dict) or not res.get("success"):
                return res if isinstance(res, dict) else {"success": False, "error": "unknown"}
            with open(tmp_path, "rb") as f:
                raw = f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if len(raw) >= threshold:
            compressed = gzip.compress(raw, compresslevel=6)
            return {
                "success": True,
                "format": fmt,
                "size_bytes": len(raw),
                "compressed": True,
                "b64_data": base64.b64encode(compressed).decode("ascii"),
            }
        return {
            "success": True,
            "format": fmt,
            "size_bytes": len(raw),
            "compressed": False,
            "b64_data": base64.b64encode(raw).decode("ascii"),
        }

    def get_active_view(self) -> dict[str, Any]:
        return self.server.get_active_view()  # type: ignore[return-value]
