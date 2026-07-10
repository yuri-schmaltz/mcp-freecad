"""Unit tests for the Pydantic request schemas.

These schemas sit between the MCP tool layer and the FreeCAD RPC
client. A failure here must surface as a clear error to the LLM, not
a vague FreeCAD fault.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.schemas import (  # noqa: E402
    validate_create_object,
    validate_edit_object,
)


# --- CreateObjectRequest ------------------------------------------------

def test_create_object_minimal():
    req = validate_create_object({
        "doc_name": "MyDoc",
        "obj_type": "Part::Box",
        "obj_name": "Box",
    })
    assert req.doc_name == "MyDoc"
    assert req.obj_name == "Box"
    assert req.obj_type == "Part::Box"
    assert req.analysis_name is None
    assert req.obj_properties is None


def test_create_object_with_properties():
    req = validate_create_object({
        "doc_name": "MyDoc",
        "obj_type": "Part::Box",
        "obj_name": "Box",
        "obj_properties": {"Length": 10, "Width": 5},
    })
    assert req.obj_properties == {"Length": 10, "Width": 5}


def test_create_object_with_analysis():
    req = validate_create_object({
        "doc_name": "MyDoc",
        "obj_type": "Fem::MaterialCommon",
        "obj_name": "Steel",
        "analysis_name": "Analysis",
    })
    assert req.analysis_name == "Analysis"


def test_create_object_fem_type_requires_analysis():
    """Fem:: types other than Fem::AnalysisPython need an analysis."""
    with pytest.raises(ValidationError) as exc:
        validate_create_object({
            "doc_name": "Doc",
            "obj_type": "Fem::MaterialCommon",
            "obj_name": "Steel",
            # analysis_name missing
        })
    assert "analysis_name" in str(exc.value).lower()


def test_create_object_fem_analysis_python_does_not_require_analysis():
    """The container itself doesn't live in a parent analysis."""
    req = validate_create_object({
        "doc_name": "Doc",
        "obj_type": "Fem::AnalysisPython",
        "obj_name": "Analysis",
    })
    assert req.analysis_name is None


def test_create_object_rejects_empty_name():
    with pytest.raises(ValidationError):
        validate_create_object({
            "doc_name": "Doc",
            "obj_type": "Part::Box",
            "obj_name": "",
        })


def test_create_object_rejects_dotted_name():
    """FreeCAD names cannot contain dots (used as attribute accessors)."""
    with pytest.raises(ValidationError):
        validate_create_object({
            "doc_name": "Doc",
            "obj_type": "Part::Box",
            "obj_name": "Box.1",
        })


def test_create_object_rejects_extra_fields():
    """A typo in the field name should fail loudly, not be silently dropped."""
    with pytest.raises(ValidationError) as exc:
        validate_create_object({
            "doc_name": "Doc",
            "obj_type": "Part::Box",
            "obj_name": "Box",
            "obj_propertie": {"Length": 10},  # missing 's'
        })
    assert "obj_propertie" in str(exc.value)


def test_create_object_strips_whitespace():
    req = validate_create_object({
        "doc_name": "  Doc  ",
        "obj_type": "Part::Box",
        "obj_name": "  Box  ",
    })
    assert req.doc_name == "Doc"
    assert req.obj_name == "Box"


# --- EditObjectRequest --------------------------------------------------

def test_edit_object_minimal():
    req = validate_edit_object({
        "doc_name": "Doc",
        "obj_name": "Box",
        "obj_properties": {"Length": 20},
    })
    assert req.obj_properties == {"Length": 20}


def test_edit_object_rejects_missing_properties():
    with pytest.raises(ValidationError):
        validate_edit_object({
            "doc_name": "Doc",
            "obj_name": "Box",
            # obj_properties missing
        })


def test_edit_object_rejects_extra_fields():
    with pytest.raises(ValidationError):
        validate_edit_object({
            "doc_name": "Doc",
            "obj_name": "Box",
            "obj_properties": {},
            "extra": 1,
        })


# --- integration with operations ----------------------------------------

def test_create_object_operation_rejects_bad_payload(monkeypatch):
    """The operation layer must surface a validation error as a text
    response (not raise), so the LLM gets a clear message.
    """
    from freecad_mcp.operations import core as ops

    class _FakeConn:
        def create_object(self_inner, *args, **kwargs):
            raise AssertionError("FreeCAD should not be called for invalid input")

        def get_active_screenshot(self_inner):
            return None

    result = ops.create_object_operation(
        _FakeConn(),  # type: ignore[arg-type]
        only_text_feedback=True,
        doc_name="Doc",
        obj_type="Part::Box",
        obj_name="",  # invalid: empty
    )
    assert len(result) == 1
    assert "Invalid create_object" in result[0].text


def test_create_object_operation_fem_without_analysis_blocked(monkeypatch):
    """The classic 'create Fem::Material without analysis' bug.
    """
    from freecad_mcp.operations import core as ops

    class _FakeConn:
        def create_object(self_inner, *args, **kwargs):
            raise AssertionError("should not reach FreeCAD")

        def get_active_screenshot(self_inner):
            return None

    result = ops.create_object_operation(
        _FakeConn(),  # type: ignore[arg-type]
        only_text_feedback=True,
        doc_name="Doc",
        obj_type="Fem::ConstraintFixed",
        obj_name="Fix",
        # analysis_name missing
    )
    assert "Invalid create_object" in result[0].text
    assert "analysis_name" in result[0].text.lower()


if __name__ == "__main__":
    print("Run with pytest; direct invocation is not supported.")
