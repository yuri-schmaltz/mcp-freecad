import importlib.util
from pathlib import Path


def load_serialize_module():
    p = Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP" / "rpc_server" / "serialize.py"
    spec = importlib.util.spec_from_file_location("serialize_mod", str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_serialize_vector_rotation_placement_and_object():
    mod = load_serialize_module()

    # Define fake FreeCAD-like classes and register them on the module's App
    class V:
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z

    class Axis:
        def __init__(self, x, y, z):
            self.x = x
            self.y = y
            self.z = z

    class R:
        def __init__(self, axis, angle):
            self.Axis = axis
            self.Angle = angle

    class P:
        def __init__(self, base, rotation):
            self.Base = base
            self.Rotation = rotation

    # Patch the module's App so serialize recognizes the types
    mod.App.Vector = V
    mod.App.Rotation = R
    mod.App.Placement = P

    v = V(1, 2, 3)
    assert mod.serialize_value(v) == {"x": 1, "y": 2, "z": 3}

    axis = Axis(0, 0, 1)
    r = R(axis, 45)
    rv = mod.serialize_value(r)
    assert rv["Angle"] == 45
    assert rv["Axis"]["z"] == 1

    p = P(v, r)
    pv = mod.serialize_value(p)
    assert pv["Base"] == {"x": 1, "y": 2, "z": 3}
    assert pv["Rotation"]["Angle"] == 45

    # Fake object
    class FakeObj:
        Name = "Box1"
        Label = "B1"
        TypeId = "Part::Box"
        PropertiesList = ["Height"]
        Height = 10
        Placement = None
        Shape = None
        ViewObject = None

    fo = FakeObj()
    so = mod.serialize_object(fo)
    assert so["Name"] == "Box1"
    assert so["Properties"]["Height"] == 10
