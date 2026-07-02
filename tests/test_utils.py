"""Unit tests for the safe_operation decorator."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.responses import SYSTEM_DIRECTIVE_PREFIX  # noqa: E402
from freecad_mcp.utils import safe_operation  # noqa: E402


@safe_operation
def boom():
    raise RuntimeError("kaboom")


@safe_operation
def ok():
    return "fine"


def test_safe_operation_returns_text_on_exception():
    r = boom()
    assert len(r) == 1
    assert r[0].type == "text"
    assert "Internal server error" in r[0].text
    assert "boom" in r[0].text
    assert r[0].text.startswith(SYSTEM_DIRECTIVE_PREFIX)


def test_safe_operation_passes_through_on_success():
    r = ok()
    assert r == "fine"


if __name__ == "__main__":
    test_safe_operation_returns_text_on_exception()
    test_safe_operation_passes_through_on_success()
    print("All utils tests passed")
