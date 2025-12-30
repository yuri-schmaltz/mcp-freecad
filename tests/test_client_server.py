import pytest
from src.freecad_mcp.server import FreeCADConnection

def test_create_document_validation():
    conn = FreeCADConnection()
    with pytest.raises(ValueError):
        conn.create_document("")
    with pytest.raises(ValueError):
        conn.create_document(None)

def test_create_object_validation():
    conn = FreeCADConnection()
    with pytest.raises(ValueError):
        conn.create_object("", {})
    with pytest.raises(ValueError):
        conn.create_object("doc", None)

def test_edit_object_validation():
    conn = FreeCADConnection()
    with pytest.raises(ValueError):
        conn.edit_object("", "obj", {})
    with pytest.raises(ValueError):
        conn.edit_object("doc", "", {})
    with pytest.raises(ValueError):
        conn.edit_object("doc", "obj", None)

def test_delete_object_validation():
    conn = FreeCADConnection()
    with pytest.raises(ValueError):
        conn.delete_object("", "obj")
    with pytest.raises(ValueError):
        conn.delete_object("doc", "")

def test_insert_part_from_library_validation():
    conn = FreeCADConnection()
    with pytest.raises(ValueError):
        conn.insert_part_from_library("")
    with pytest.raises(ValueError):
        conn.insert_part_from_library(None)
