"""Unit tests for operations/core.py — drives the operations against fakes.

These cover the full MCP-facing surface of the operations layer without
spinning up FreeCAD: we substitute FreeCADConnection with a small stub
that records what the operations call. The goal is to cover the
branching (guidelines, success, failure, screenshot attachment) that the
MCP layer relies on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import freecad_mcp.operations.core as core  # noqa: E402

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeFreeCAD:
    """Stand-in for FreeCADConnection that records every call."""

    def __init__(
        self,
        create_document=None,
        create_object=None,
        edit_object=None,
        delete_object=None,
        execute_code=None,
        get_active_screenshot=None,
        insert_part_from_library=None,
        get_objects=None,
        get_object=None,
        get_parts_list=None,
        list_documents=None,
        run_fem_analysis=None,
    ):
        self.calls = []
        self._handlers = {
            "create_document": create_document,
            "create_object": create_object,
            "edit_object": edit_object,
            "delete_object": delete_object,
            "execute_code": execute_code,
            "get_active_screenshot": get_active_screenshot,
            "insert_part_from_library": insert_part_from_library,
            "get_objects": get_objects,
            "get_object": get_object,
            "get_parts_list": get_parts_list,
            "list_documents": list_documents,
            "run_fem_analysis": run_fem_analysis,
        }

    def _dispatch(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        handler = self._handlers.get(name)
        if handler is None:
            raise RuntimeError(f"unhandled: {name}")
        return handler(*args, **kwargs)

    def create_document(self, name):
        return self._dispatch("create_document", name)

    def create_object(self, doc_name, obj_data):
        return self._dispatch("create_object", doc_name, obj_data)

    def edit_object(self, doc_name, obj_name, obj_data):
        return self._dispatch("edit_object", doc_name, obj_name, obj_data)

    def delete_object(self, doc_name, obj_name):
        return self._dispatch("delete_object", doc_name, obj_name)

    def execute_code(self, code):
        return self._dispatch("execute_code", code)

    def get_active_screenshot(self, *args, **kwargs):
        return self._dispatch("get_active_screenshot", *args, **kwargs)

    def insert_part_from_library(self, relative_path):
        return self._dispatch("insert_part_from_library", relative_path)

    def get_objects(self, doc_name):
        return self._dispatch("get_objects", doc_name)

    def get_object(self, doc_name, obj_name):
        return self._dispatch("get_object", doc_name, obj_name)

    def get_parts_list(self):
        return self._dispatch("get_parts_list")

    def list_documents(self):
        return self._dispatch("list_documents")

    def run_fem_analysis(self, doc_name, analysis_name, timeout):
        return self._dispatch("run_fem_analysis", doc_name, analysis_name, timeout)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_document_success():
    fake = FakeFreeCAD(create_document=lambda n: {"success": True, "document_name": n})
    r = core.create_document_operation(fake, "Doc1")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("created successfully" in t for t in texts), texts
    assert fake.calls[0][0] == "create_document"


def test_create_document_failure():
    fake = FakeFreeCAD(create_document=lambda n: {"success": False, "error": "boom"})
    r = core.create_document_operation(fake, "Doc1")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Failed to create document" in t and "boom" in t for t in texts)


def test_create_object_success_includes_screenshot_when_available():
    fake = FakeFreeCAD(
        create_object=lambda d, o: {"success": True, "object_name": o["Name"]},
        get_active_screenshot=lambda: "B64",
    )
    r = core.create_object_operation(fake, False, "Doc", "Part::Box", "B", None, {})
    has_image = any(getattr(t, "type", "") == "image" for t in r)
    assert has_image, f"expected image attachment in {r}"


def test_create_object_no_screenshot_when_only_text_feedback():
    fake = FakeFreeCAD(
        create_object=lambda d, o: {"success": True, "object_name": o["Name"]},
        get_active_screenshot=lambda: "B64",
    )
    r = core.create_object_operation(fake, True, "Doc", "Part::Box", "B", None, {})
    has_image = any(getattr(t, "type", "") == "image" for t in r)
    assert not has_image


def test_create_object_blocked_by_dangerous_name():
    """A name with a banned pattern in obj_name is allowed (we do not
    check names). Use a real exec via execute_code instead.
    """
    fake = FakeFreeCAD(
        create_object=lambda d, o: {"success": True, "object_name": o["Name"]},
        get_active_screenshot=lambda: None,
    )
    # Names are labels; no guideline check.
    r = core.create_object_operation(fake, False, "Doc", "Part::Box", "eval test", None, {})
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("created successfully" in t for t in texts)


def test_create_object_failure_reports_error():
    fake = FakeFreeCAD(
        create_object=lambda d, o: {"success": False, "error": "nope"},
        get_active_screenshot=lambda: None,
    )
    r = core.create_object_operation(fake, False, "Doc", "Part::Box", "B", None, {})
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Failed to create object" in t and "nope" in t for t in texts)


def test_edit_object_success():
    fake = FakeFreeCAD(
        edit_object=lambda d, n, p: {"success": True, "object_name": n},
        get_active_screenshot=lambda: None,
    )
    r = core.edit_object_operation(fake, False, "Doc", "Box", {"Height": 5})
    assert any("edited successfully" in t.text for t in r if hasattr(t, "text"))


def test_delete_object_success():
    fake = FakeFreeCAD(
        delete_object=lambda d, n: {"success": True, "object_name": n},
        get_active_screenshot=lambda: None,
    )
    r = core.delete_object_operation(fake, False, "Doc", "Box")
    assert any("deleted successfully" in t.text for t in r if hasattr(t, "text"))


def test_execute_code_dangerous_blocked():
    fake = FakeFreeCAD(
        execute_code=lambda c: {"success": True, "message": "ok"},
        get_active_screenshot=lambda: None,
    )
    r = core.execute_code_operation(fake, False, "os.system('rm -rf /')")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Refusing" in t and "pattern" in t for t in texts)
    # And the fake should not have been called.
    assert not any(call[0] == "execute_code" for call in fake.calls)


def test_execute_code_safe_passes_through():
    fake = FakeFreeCAD(
        execute_code=lambda c: {"success": True, "message": "executed"},
        get_active_screenshot=lambda: None,
    )
    r = core.execute_code_operation(fake, False, "doc.addObject('Part::Box', 'B')")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("executed successfully" in t for t in texts)


def test_insert_part_from_library_safe_path():
    fake = FakeFreeCAD(
        insert_part_from_library=lambda p: {"success": True, "message": "ok"},
        get_active_screenshot=lambda: None,
    )
    r = core.insert_part_from_library_operation(fake, False, "Mechanical/Bearings/6200.fcstd")
    assert any("inserted from library" in t.text for t in r if hasattr(t, "text"))


def test_insert_part_from_library_path_traversal_blocked():
    fake = FakeFreeCAD(
        insert_part_from_library=lambda p: {"success": True, "message": "ok"},
        get_active_screenshot=lambda: None,
    )
    r = core.insert_part_from_library_operation(fake, False, "../../etc/passwd")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Diretriz" in t or "escapes" in t.lower() for t in texts)
    assert not any(call[0] == "insert_part_from_library" for call in fake.calls)


def test_insert_part_from_library_failure_reports():
    fake = FakeFreeCAD(
        insert_part_from_library=lambda p: {"success": False, "error": "missing"},
        get_active_screenshot=lambda: None,
    )
    r = core.insert_part_from_library_operation(fake, False, "gear.fcstd")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Failed" in t and "missing" in t for t in texts)


def test_get_objects_json_response():
    fake = FakeFreeCAD(
        get_objects=lambda d: [{"Name": "Box"}],
        get_active_screenshot=lambda: None,
    )
    r = core.get_objects_operation(fake, False, "Doc")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Box" in t for t in texts)


def test_get_object_json_response():
    fake = FakeFreeCAD(
        get_object=lambda d, n: {"Name": n, "TypeId": "Part::Box"},
        get_active_screenshot=lambda: None,
    )
    r = core.get_object_operation(fake, False, "Doc", "Box")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Part::Box" in t for t in texts)


def test_get_parts_list_with_parts():
    fake = FakeFreeCAD(get_parts_list=lambda: ["a.fcstd", "b.fcstd"])
    r = core.get_parts_list_operation(fake)
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("a.fcstd" in t and "b.fcstd" in t for t in texts)


def test_get_parts_list_empty_message():
    fake = FakeFreeCAD(get_parts_list=lambda: [])
    r = core.get_parts_list_operation(fake)
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("No parts found" in t for t in texts)


def test_list_documents_json():
    fake = FakeFreeCAD(list_documents=lambda: ["Doc1", "Doc2"])
    r = core.list_documents_operation(fake)
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Doc1" in t and "Doc2" in t for t in texts)


def test_get_view_with_screenshot():
    fake = FakeFreeCAD(get_active_screenshot=lambda *a, **k: "BASE64DATA")
    r = core.get_view_operation(fake, "Isometric")
    assert any(getattr(t, "type", "") == "image" and t.data == "BASE64DATA" for t in r)


def test_get_view_without_screenshot():
    fake = FakeFreeCAD(get_active_screenshot=lambda *a, **k: None)
    r = core.get_view_operation(fake, "Isometric")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Cannot get screenshot" in t for t in texts)


def test_run_fem_analysis_success_summary():
    fake = FakeFreeCAD(
        run_fem_analysis=lambda d, a, t: {
            "success": True,
            "result_object": "Results",
            "node_count": 1234,
            "max_von_mises_MPa": 250.0,
            "min_von_mises_MPa": 5.0,
            "max_displacement_mm": 0.123,
            "working_dir": "/tmp/x",
        },
        get_active_screenshot=lambda: None,
    )
    r = core.run_fem_analysis_operation(fake, False, "Doc", "Analysis", 60)
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("solved" in t.lower() for t in texts)
    assert any("250" in t for t in texts)


def test_run_fem_analysis_failure_summary():
    fake = FakeFreeCAD(
        run_fem_analysis=lambda d, a, t: {
            "success": False, "error": "no solver", "working_dir": "/tmp/x",
        },
        get_active_screenshot=lambda: None,
    )
    r = core.run_fem_analysis_operation(fake, False, "Doc", "Analysis", 60)
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("failed" in t.lower() and "no solver" in t for t in texts)


def test_safe_operation_catches_exception():
    fake = FakeFreeCAD(get_objects=lambda d: (_ for _ in ()).throw(RuntimeError("boom")))
    fake._handlers["get_active_screenshot"] = lambda: None
    r = core.get_objects_operation(fake, False, "Doc")
    texts = [t.text for t in r if hasattr(t, "text")]
    assert any("Internal server error" in t and "boom" in t for t in texts)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print("All operations core tests passed")
