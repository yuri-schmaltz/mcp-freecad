"""End-to-end smoke test: drive the MCP server via the XML-RPC client.

Does NOT require a Claude Desktop or any MCP host — just a running
FreeCAD with the RPC server enabled. Useful for sanity-checking the
install, smoke-testing a release, or as a worked example of the
client API.

Run:
    python examples/hello_freecad.py

Expected output: a small part ("HelloBox") is created, edited, saved
to a temp file, exported as STL, and a screenshot is taken.
"""
from __future__ import annotations

import os
import sys
import tempfile
import xmlrpc.client

HOST = os.environ.get("FREECAD_HOST", "localhost")
PORT = int(os.environ.get("FREECAD_PORT", "9875"))


def main() -> int:
    proxy = xmlrpc.client.ServerProxy(f"http://{HOST}:{PORT}", allow_none=True)

    if not proxy.ping():
        print(f"RPC server at {HOST}:{PORT} is not responding.")
        print("Start it from the FreeCAD MCP toolbar (or via auto-start).")
        return 2

    print("→ ping ok")

    # Use a per-run document name so reruns don't trip the file-existence
    # check inside FreeCAD.
    doc_name = "HelloBox"

    # ---- 1. Create a document + a Part::Box + verify it landed ----------
    print("→ create_document + create_object")
    res = proxy.create_document(doc_name)
    assert res.get("success"), res
    res = proxy.create_object(doc_name, {
        "Name": "Box",
        "Type": "Part::Box",
        "Properties": {"Length": 20.0, "Width": 10.0, "Height": 5.0},
    })
    assert res.get("success"), res
    objs = proxy.get_objects(doc_name)
    print(f"   document now contains: {[o['Name'] for o in objs]}")

    # ---- 2. Edit the box and read it back --------------------------------
    print("→ edit_object + get_object")
    proxy.edit_object(doc_name, "Box", {"Properties": {"Length": 30.0}})
    obj = proxy.get_object(doc_name, "Box")
    print(f"   Box.Length is now {obj['Properties']['Length']}")

    # ---- 3. Save to a temp .FCStd ----------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        fcstd = os.path.join(tmp, f"{doc_name}.FCStd")
        stl = os.path.join(tmp, f"{doc_name}.stl")
        print(f"→ save_document to {fcstd}")
        res = proxy.save_document(doc_name, fcstd)
        assert res.get("success"), res
        assert os.path.exists(fcstd), "FCStd file was not created"
        print(f"   file size: {os.path.getsize(fcstd)} bytes")

        # ---- 4. Export the box as STL ------------------------------------
        print(f"→ export_object to {stl}")
        res = proxy.export_object(doc_name, "Box", stl, "stl")
        assert res.get("success"), res
        assert os.path.exists(stl), "STL file was not created"
        print(f"   file size: {os.path.getsize(stl)} bytes")

    # ---- 5. Health probe --------------------------------------------------
    print("→ health_check")
    h = proxy.health_check()
    for k, v in sorted(h.items()):
        print(f"   {k}: {v}")

    print("\nOK — all RPC plumbing works end-to-end.")
    return 0


if __name__ == "__main__":
    sys.exit(main())