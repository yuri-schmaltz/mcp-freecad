"""Aggregate runner: executes every standalone unit-test module in tests/.

This lets the CI run with plain ``python -u tests/run_all_tests.py`` while
the codebase migrates to pytest (planned in IMPROVEMENT_PLAN.md Phase 4).
Each test module's ``__main__`` block returns ``None`` on success and
raises on failure, matching the existing convention.

Modules that require FreeCAD at runtime are skipped here.
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

MODULES = [
    "tests.run_guidelines_tests",       # legacy runner (kept for back-compat)
    "tests.test_guidelines",
    "tests.test_responses",
    "tests.test_utils",
    "tests.test_serialize",
    "tests.test_validate_allowed_ips",
    "tests.test_fem_workdir_cleanup",
    "tests.test_parts_library",
    "tests.test_freecad_client",
]


def _run(modname: str) -> None:
    spec = importlib.util.spec_from_file_location(
        modname, HERE / f"{modname.split('.', 1)[1]}.py"
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load spec for {modname}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # Re-run the module's own assertions if present.
    if hasattr(mod, "__main__"):
        # Already executed on import via the __main__ guard when run as
        # a script; running the test functions explicitly gives us a clear
        # per-module summary even when imported.
        test_funcs = [
            (n, f) for n, f in vars(mod).items()
            if n.startswith("test_") and callable(f)
        ]
        for name, fn in test_funcs:
            fn()


def main() -> int:
    failed = []
    for modname in MODULES:
        print(f"--- {modname} ---")
        try:
            _run(modname)
        except Exception as e:  # noqa: BLE001
            failed.append((modname, e))
            print(f"FAIL: {modname}: {type(e).__name__}: {e}")
        else:
            print(f"PASS: {modname}")
    print()
    if failed:
        print(f"{len(failed)} module(s) failed:")
        for m, e in failed:
            print(f"  - {m}: {type(e).__name__}: {e}")
        return 1
    print(f"All {len(MODULES)} test modules passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())