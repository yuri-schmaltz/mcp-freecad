ASSET_CREATION_STRATEGY = """\
FreeCAD asset workflow (compact):

0. Before any task: call get_objects() to see the current document.
1. Prefer the parts library: get_parts_list() → insert_part_from_library() if available.
2. Otherwise create primitives with create_object() (Box, Cylinder, Sphere, …) and refine with edit_object().
3. Use descriptive names. Always set Placement explicitly via edit_object() so the spatial layout is intentional.
4. After editing, verify with get_object() that the property stuck.
5. Use execute_code() only for things the structured tools cannot express (FEM, scripted geometry, custom ops). The code is run in-process on the FreeCAD GUI thread and runs whatever Python the model chooses to submit; the server applies a regex-based blocklist to a handful of dangerous builtins (eval, exec, os.system, subprocess, shutdown, reboot) — see ``check_code_conflict`` in ``guidelines.py`` for the full list.
"""
