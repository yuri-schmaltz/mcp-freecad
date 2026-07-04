"""Full coverage tests for addon/FreeCADMCP/rpc_server/serialize.py.

serialize.py is mostly pure (it only depends on FreeCAD for type
introspection) so we exercise every branch directly.
"""
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

# Set up FreeCAD with the types serialize.py introspects.
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
_fc.Vector = type("Vector", (), {"x": 0, "y": 0, "z": 0})
_fc.Rotation = type("Rotation", (), {})
_fc.Placement = type("Placement", (), {})

# Mock the Color type
class _Color:
    def __init__(self, r, g, b, a=1.0):
        self.r, self.g, self.b, self.a = r, g, b, a
    def __iter__(self):
        return iter([self.r, self.g, self.b, self.a])
_fc.Color = _Color

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


def _load_serialize():
    spec = importlib.util.spec_from_file_location(
        "serialize_under_test", str(_RS_DIR / "serialize.py")
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


s = _load_serialize()


# ---------------------------------------------------------------------------
# serialize_value
# ---------------------------------------------------------------------------

def test_serialize_primitives():
    assert s.serialize_value(1) == 1
    assert s.serialize_value(1.5) == 1.5
    assert s.serialize_value("x") == "x"
    assert s.serialize_value(True) is True


def test_serialize_unknown_falls_back_to_str():
    """Anything we don't recognise is stringified."""
    class Mystery:
        def __str__(self):
            return "mystery!"
    assert s.serialize_value(Mystery()) == "mystery!"


def test_serialize_list_and_tuple():
    """Lists and tuples are recursed."""
    class V:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z
    s.App.Vector = V
    v = V(1, 2, 3)
    out = s.serialize_value([v, v, "tail"])
    assert out == [{"x": 1, "y": 2, "z": 3}, {"x": 1, "y": 2, "z": 3}, "tail"]


def test_serialize_color():
    """Color objects are converted to a 4-tuple."""
    assert s.serialize_value(_Color(0.1, 0.2, 0.3, 0.4)) == (0.1, 0.2, 0.3, 0.4)


# ---------------------------------------------------------------------------
# serialize_shape
# ---------------------------------------------------------------------------

class _Shape:
    def __init__(self, v, a, n_verts=0, n_edges=0, n_faces=0):
        self.Volume = v
        self.Area = a
        self.Vertexes = list(range(n_verts))
        self.Edges = list(range(n_edges))
        self.Faces = list(range(n_faces))


def test_serialize_shape_with_counts():
    shape = _Shape(v=12.5, a=34.0, n_verts=8, n_edges=12, n_faces=6)
    out = s.serialize_shape(shape)
    assert out == {"Volume": 12.5, "Area": 34.0, "VertexCount": 8, "EdgeCount": 12, "FaceCount": 6}


def test_serialize_shape_none_returns_none():
    assert s.serialize_shape(None) is None


def test_serialize_shape_with_none_counts():
    """If Vertexes/Edges/Faces are None, the counts are 0."""
    shape = types.SimpleNamespace(Volume=1.0, Area=1.0, Vertexes=None, Edges=None, Faces=None)
    out = s.serialize_shape(shape)
    assert out["VertexCount"] == 0
    assert out["EdgeCount"] == 0
    assert out["FaceCount"] == 0


# ---------------------------------------------------------------------------
# serialize_view_object
# ---------------------------------------------------------------------------

class _ViewObj:
    def __init__(self, color, transparency, visibility):
        self.ShapeColor = color
        self.Transparency = transparency
        self.Visibility = visibility


def test_serialize_view_object_basic():
    v = _ViewObj((0.1, 0.2, 0.3, 0.4), 50, True)
    out = s.serialize_view_object(v)
    # ShapeColor comes back as a list (serialize_value recurses through
    # the list/tuple branch) — the test pins the loose shape.
    assert out["ShapeColor"] == [0.1, 0.2, 0.3, 0.4]
    assert out["Transparency"] == 50
    assert out["Visibility"] is True


def test_serialize_view_object_none():
    assert s.serialize_view_object(None) is None


# ---------------------------------------------------------------------------
# serialize_object
# ---------------------------------------------------------------------------

def _make_obj(name="Box", label="B", type_id="Part::Box", properties=None,
              placement=None, shape=None, view=None):
    return types.SimpleNamespace(
        Name=name, Label=label, TypeId=type_id,
        PropertiesList=list((properties or {}).keys()),
        Placement=placement,
        Shape=shape,
        ViewObject=view,
        **{k: v for k, v in (properties or {}).items()},
    )


def test_serialize_object_basic():
    obj = _make_obj(properties={"Height": 10, "Width": 20})
    out = s.serialize_object(obj)
    assert out["Name"] == "Box"
    assert out["Label"] == "B"
    assert out["TypeId"] == "Part::Box"
    assert out["Properties"] == {"Height": 10, "Width": 20}


def test_serialize_object_list():
    obj = _make_obj(properties={"Height": 1})
    out = s.serialize_object([obj, obj])
    assert len(out) == 2
    assert all(o["Name"] == "Box" for o in out)


def test_serialize_object_doc_like():
    """A document-like object (has 'Objects' and 'Name') is recursed."""
    child = _make_obj(name="Child", properties={})
    doc = types.SimpleNamespace(
        Name="MyDoc",
        Label="MD",
        FileName="/tmp/x.FCStd",
        Objects=[child],
    )
    out = s.serialize_object(doc)
    assert out["Name"] == "MyDoc"
    assert out["Label"] == "MD"
    assert out["FileName"] == "/tmp/x.FCStd"
    assert len(out["Objects"]) == 1
    assert out["Objects"][0]["Name"] == "Child"


def test_serialize_object_handles_property_error():
    """If a property getter raises, the entry is marked with an error marker."""
    class _ErrObj:
        Name = "Box"
        Label = "B"
        TypeId = "Part::Box"
        PropertiesList = ["broken", "Height"]
        Height = 10

        def __getattr__(self, name):
            if name == "broken":
                raise RuntimeError("nope")
            if name == "ViewObject":
                return None
            if name == "Shape":
                return None
            if name == "Placement":
                return None
            raise AttributeError(name)

    obj = _ErrObj()
    out = s.serialize_object(obj)
    assert "broken" in out["Properties"]
    assert out["Properties"]["broken"].startswith("<error:")
    assert out["Properties"]["Height"] == 10


if __name__ == "__main__":
    test_serialize_primitives()
    test_serialize_unknown_falls_back_to_str()
    test_serialize_list_and_tuple()
    test_serialize_color()
    test_serialize_shape_with_counts()
    test_serialize_shape_none_returns_none()
    test_serialize_shape_with_none_counts()
    test_serialize_view_object_basic()
    test_serialize_view_object_none()
    test_serialize_object_basic()
    test_serialize_object_list()
    test_serialize_object_doc_like()
    test_serialize_object_handles_property_error()
    print("All serialize tests passed")