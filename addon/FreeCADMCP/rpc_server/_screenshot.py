"""Screenshot capture and transcoding helpers.

Extracted from ``rpc_server`` so the Pillow transcode logic is
testable without a running FreeCAD instance. The module also owns
the view-support probe string and the PNG→JPEG/WebP transcoder.

Two helpers are exported:

* :func:`transcode_to_format` \u2014 PNG bytes \u2192 base64 JPEG/WebP (or None
  on failure / no Pillow / unsupported target).
* :data:`SCREENSHOT_SUPPORT_CHECK` \u2014 the snippet of Python we send
  to the FreeCAD GUI thread to decide whether the current view
  supports ``saveImage``. Used by :mod:`freecad_client`.

The capture side (view switching, selection, ``saveImage``) lives in
the ``FreeCADRPC`` class in :mod:`rpc_server` because it requires a
live FreeCAD context.
"""
from __future__ import annotations

import base64
import io

# The snippet we run on the GUI thread to probe whether the current
# view supports ``saveImage``. Used by the client to decide whether
# to call ``get_active_screenshot`` or fall back to a text response.
SCREENSHOT_SUPPORT_CHECK = """
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


def transcode_to_format(png_bytes: bytes, target_format: str) -> str | None:
    """Transcode a PNG byte string to JPEG or WebP via Pillow.

    Returns the base64-encoded output, or ``None`` on failure. The
    failure modes are:
    * Pillow is not installed (callers should display a clear error).
    * The target format is not ``"jpeg"``/``"jpg"``/``"webp"``.
    * Any PIL error during decode/encode.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return None
    try:
        with Image.open(io.BytesIO(png_bytes)) as img:
            buf = io.BytesIO()
            save_kwargs: dict = {}
            if target_format in ("jpeg", "jpg"):
                # JPEG cannot store alpha; flatten onto white.
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGB")
                save_kwargs["quality"] = 85
                img.save(buf, format="JPEG", **save_kwargs)
            elif target_format == "webp":
                save_kwargs["quality"] = 80
                img.save(buf, format="WEBP", **save_kwargs)
            else:
                return None
            return base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception:
        return None


__all__ = [
    "SCREENSHOT_SUPPORT_CHECK",
    "transcode_to_format",
]
