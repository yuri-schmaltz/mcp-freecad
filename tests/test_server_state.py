"""Tests for the ServerState dataclass and surrounding wiring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.server_state import ServerState  # noqa: E402


def test_defaults():
    s = ServerState()
    assert s.only_text_feedback is False
    assert s.rpc_host == "localhost"
    assert s.freecad_connection is None


def test_assignable():
    s = ServerState()
    s.only_text_feedback = True
    s.rpc_host = "10.0.0.1"
    sentinel = object()
    s.freecad_connection = sentinel
    assert s.only_text_feedback is True
    assert s.rpc_host == "10.0.0.1"
    assert s.freecad_connection is sentinel


if __name__ == "__main__":
    test_defaults()
    test_assignable()
    print("All server_state tests passed")
