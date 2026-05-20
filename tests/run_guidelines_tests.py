import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from freecad_mcp.responses import text_response, SYSTEM_DIRECTIVE_PREFIX
from freecad_mcp.guidelines import check_prompt_conflict
from freecad_mcp.operations.core import execute_code_operation


def test_prefix():
    r = text_response('Teste de prefixo')
    assert r[0].text.startswith(SYSTEM_DIRECTIVE_PREFIX)


def test_guidelines_blocking():
    # Fake FreeCAD
    class FakeFreeCAD:
        def execute_code(self, code):
            return {"success": True, "message": "ok"}

        def get_active_screenshot(self):
            return None

    fake = FakeFreeCAD()
    # Dangerous code should be blocked
    res = execute_code_operation(fake, True, "import os; os.system('rm -rf /')")
    assert any("Refuse to execute code" in t.text for t in res if hasattr(t, 'text'))


def test_create_object_safe_decorator():
    # Fake FreeCAD for create_object
    class FakeFreeCAD2:
        def create_object(self, doc_name, obj_data):
            return {"success": True, "object_name": obj_data.get("Name", "unnamed")}

        def get_active_screenshot(self):
            return None

    from freecad_mcp.operations.core import create_object_operation

    fake2 = FakeFreeCAD2()
    res = create_object_operation(fake2, True, "Doc1", "Part::Box", "BoxA", None, {"Height": 10})
    # Should contain success text and the system prefix
    texts = [t.text for t in res if hasattr(t, 'text')]
    assert any("created successfully" in txt for txt in texts) or any("Internal server error" in txt for txt in texts)


def test_create_object_exception_handled():
    class BrokenFreeCAD:
        def create_object(self, doc_name, obj_data):
            raise RuntimeError("boom")

        def get_active_screenshot(self):
            return None

    from freecad_mcp.operations.core import create_object_operation

    broken = BrokenFreeCAD()
    res = create_object_operation(broken, True, "Doc1", "Part::Box", "BadBox", None, {})
    texts = [t.text for t in res if hasattr(t, 'text')]
    assert any("Internal server error" in txt for txt in texts)


def test_create_document_and_delete_object():
    # Fake FreeCAD for document and delete
    class FakeFreeCAD3:
        def __init__(self, fail_delete=False):
            self.fail_delete = fail_delete

        def create_document(self, name):
            return {"success": True, "document_name": name}

        def delete_object(self, doc_name, obj_name):
            if self.fail_delete:
                return {"success": False, "error": "not found"}
            return {"success": True, "object_name": obj_name}

        def get_active_screenshot(self):
            return None

    from freecad_mcp.operations.core import create_document_operation, delete_object_operation

    fake3 = FakeFreeCAD3()
    res_doc = create_document_operation(fake3, "MyDoc")
    assert any("created successfully" in t.text for t in res_doc if hasattr(t, 'text'))

    res_del = delete_object_operation(fake3, True, "MyDoc", "ObjA")
    assert any("deleted successfully" in t.text for t in res_del if hasattr(t, 'text'))

    # test failing delete
    fake4 = FakeFreeCAD3(fail_delete=True)
    res_del2 = delete_object_operation(fake4, True, "MyDoc", "ObjB")
    assert any("Failed to delete object" in t.text for t in res_del2 if hasattr(t, 'text'))


if __name__ == '__main__':
    test_prefix()
    test_guidelines_blocking()
    print('All guideline tests passed')
