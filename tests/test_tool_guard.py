"""Integration test for the _guard_tool decorator.

The decorator must:
* Pass through to the original function when the tool is enabled.
* Return a text_response error when the tool is disabled.
* Preserve __name__ / __doc__ so the FastMCP layer can introspect.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


import freecad_mcp.tool_policy as _policy_mod  # noqa: E402
import freecad_mcp.server as server  # noqa: E402


def test_disabled_tool_returns_error(monkeypatch):
    """When the policy disables a tool, calling it returns an error text."""
    monkeypatch.setenv("FREECAD_MCP_DISABLED_TOOLS", "execute_code")
    # Re-resolve the policy in the server module.
    server._tool_policy = _policy_mod.resolve_tool_policy()
    try:
        # Call the guarded wrapper directly (bypassing the @mcp.tool layer).
        # We don't actually need FreeCAD — the guard short-circuits before
        # the body runs.
        result = server.execute_code(None, code="print('hi')")
        assert len(result) == 1
        assert result[0].type == "text"
        assert "disabled by the server" in result[0].text
        assert "execute_code" in result[0].text
    finally:
        monkeypatch.delenv("FREECAD_MCP_DISABLED_TOOLS", raising=False)
        server._tool_policy = _policy_mod.resolve_tool_policy()


def test_enabled_tool_calls_through(monkeypatch):
    """When the policy allows a tool, the guard does not interfere.

    We mock the underlying FreeCAD client so the body of list_documents
    can run without a real FreeCAD instance; the point is to confirm
    the guard does not short-circuit when the tool is enabled.
    """
    class _FakeResponse:
        def __init__(self, data):
            self._data = data
        def __iter__(self):
            return iter(self._data)

    class _FakeList:
        def __call__(self):
            return ["Doc1", "Doc2"]

    def _fake_list_documents():
        return _FakeList()()

    import freecad_mcp.operations.core as ops
    # The tool body calls list_documents_operation(get_freecad_connection()).
    # Mock at the connection level so the body returns a fake list without
    # touching the network.
    class _FakeConn:
        def list_documents(self_inner):
            return ["Doc1", "Doc2"]

    monkeypatch.setattr(server, "get_freecad_connection", lambda: _FakeConn())
    monkeypatch.setattr(ops, "list_documents_operation", _fake_list_documents)
    result = server.list_documents(None)
    assert len(result) >= 1
    text = result[0].text if hasattr(result[0], "text") else ""
    assert "disabled by the server" not in text
    # And the underlying fake list should have been serialised.
    assert "Doc1" in text or "Doc2" in text


def test_guard_preserves_metadata():
    """_guard_tool uses functools.wraps so FastMCP sees the original
    function name and docstring.
    """
    assert server.execute_code.__name__ == "execute_code"
    assert server.execute_code.__doc__ is not None
    assert "Execute arbitrary Python code" in server.execute_code.__doc__


if __name__ == "__main__":
    print("Run with pytest; direct invocation is not supported.")
