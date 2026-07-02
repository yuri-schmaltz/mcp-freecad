import logging
from typing import Any

try:
    from mcp.types import ImageContent  # type: ignore
except Exception:
    from dataclasses import dataclass

    @dataclass  # type: ignore[no-redef]
    class ImageContent:
        type: str
        data: str
        mimeType: str

from ..freecad_client import FreeCADConnection
from ..guidelines import check_code_conflict, check_path_conflict
from ..responses import ToolResponse, add_screenshot_if_available, json_response, text_response
from ..utils import safe_operation

logger = logging.getLogger("FreeCADMCPserver")


@safe_operation
def create_document_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    # Document names are free-form labels — we do not scan them for code-style
    # dangerous tokens (which would block legitimate names like "eval test").
    res = freecad.create_document(name)
    if res.get("success"):
        return text_response(f"Document '{res['document_name']}' created successfully")
    return text_response(f"Failed to create document: {res.get('error')}")


@safe_operation
def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> ToolResponse:
    # Object names are also labels; no guidelines check here.
    obj_data = {
        "Name": obj_name,
        "Type": obj_type,
        "Properties": obj_properties or {},
        "Analysis": analysis_name,
    }
    res = freecad.create_object(doc_name, obj_data)
    screenshot = freecad.get_active_screenshot()

    if res["success"]:
        response = text_response(f"Object '{res['object_name']}' created successfully")
    else:
        response = text_response(f"Failed to create object: {res['error']}")
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
) -> ToolResponse:
    res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
    screenshot = freecad.get_active_screenshot()

    if res["success"]:
        response = text_response(f"Object '{res['object_name']}' edited successfully")
    else:
        response = text_response(f"Failed to edit object: {res['error']}")
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    res = freecad.delete_object(doc_name, obj_name)
    screenshot = freecad.get_active_screenshot()

    if res.get("success"):
        response = text_response(f"Object '{res['object_name']}' deleted successfully")
    else:
        response = text_response(f"Failed to delete object: {res.get('error')}")
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
) -> ToolResponse:
    # This is the only field where the code-style dangerous patterns apply,
    # because the value is forwarded directly to FreeCAD's Python exec().
    conflict, msg = check_code_conflict(code or "")
    if conflict:
        logger.warning("execute_code blocked by guidelines: %s", msg)
        return text_response(msg)

    res = freecad.execute_code(code)
    screenshot = freecad.get_active_screenshot()

    if res["success"]:
        response = text_response(f"Code executed successfully: {res['message']}")
    else:
        response = text_response(f"Failed to execute code: {res['error']}")
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
    if screenshot is not None:
        return [ImageContent(type="image", data=screenshot, mimeType="image/png")]
    return text_response("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")


@safe_operation
def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    relative_path: str,
) -> ToolResponse:
    # Path-specific guard runs here; the authoritative realpath check happens
    # in the addon (parts_library._safe_resolve), but failing early gives a
    # better error message to the LLM.
    conflict, msg = check_path_conflict(relative_path or "")
    if conflict:
        logger.warning("insert_part_from_library blocked by guidelines: %s", msg)
        return text_response(
            f"Diretriz: {msg} Forneça um caminho relativo dentro da parts library."
        )

    res = freecad.insert_part_from_library(relative_path)
    screenshot = freecad.get_active_screenshot()

    if res.get("success"):
        response = text_response(f"Part inserted from library: {res.get('message')}")
    else:
        response = text_response(f"Failed to insert part from library: {res.get('error')}")
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot()
    response = json_response(freecad.get_objects(doc_name))
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot()
    response = json_response(freecad.get_object(doc_name, obj_name))
    return add_screenshot_if_available(response, screenshot, only_text_feedback)


@safe_operation
def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    parts = freecad.get_parts_list()
    if parts:
        return json_response(parts)
    return text_response("No parts found in the parts library. You must add parts_library addon.")


@safe_operation
def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


@safe_operation
def run_fem_analysis_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    analysis_name: str,
    timeout: int = 600,
) -> ToolResponse:
    res = freecad.run_fem_analysis(doc_name, analysis_name, timeout)
    if res.get("success"):
        def fmt(v, unit):
            return f"{v:.4g} {unit}" if isinstance(v, (int, float)) else f"unavailable ({unit})"
        screenshot = freecad.get_active_screenshot() if not only_text_feedback else None
        response = json_response({
            "summary": (
                f"FEM analysis '{analysis_name}' solved. "
                f"max von Mises = {fmt(res.get('max_von_mises_MPa'), 'MPa')}, "
                f"max displacement = {fmt(res.get('max_displacement_mm'), 'mm')} "
                f"({res.get('node_count')} nodes)."
            ),
            **res,
        })
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    return json_response({
        "summary": f"FEM analysis '{analysis_name}' failed: {res.get('error')}",
        **res,
    })
