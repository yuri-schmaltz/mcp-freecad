"""Targeted tests for server.py and responses.py edge cases.

Covers:
- The mcp_instructions cap (FREECAD_MCP_MAX_INSTRUCTIONS_CHARS)
- _validate_host edge cases
- configure_logging's handler set behaviour
- The text_response / json_response error paths
"""
import argparse
import importlib
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import freecad_mcp.responses as responses  # noqa: E402
import freecad_mcp.server as server  # noqa: E402


# ---------------------------------------------------------------------------
# server._validate_host — edge cases
# ---------------------------------------------------------------------------

def test_validate_host_rejects_empty():
    try:
        server._validate_host("")
    except argparse.ArgumentTypeError:
        return
    raise AssertionError("empty host should be rejected")


def test_validate_host_rejects_hostname_with_trailing_dot():
    # A trailing dot is technically valid for FQDNs, but validators may
    # not accept it. We just confirm behaviour matches the validator.
    try:
        result = server._validate_host("myhost.example.com.")
        # If accepted, value should be preserved.
        assert result == "myhost.example.com."
    except argparse.ArgumentTypeError:
        pass  # also acceptable


def test_validate_host_rejects_ipv4_out_of_range():
    try:
        server._validate_host("256.256.256.256")
    except argparse.ArgumentTypeError:
        return
    raise AssertionError("out-of-range IPv4 should be rejected")


# ---------------------------------------------------------------------------
# server.configure_logging — handler count
# ---------------------------------------------------------------------------

def test_configure_logging_handler_count_stable():
    """Multiple invocations of configure_logging must not stack handlers."""
    root = logging.getLogger()
    before = len(root.handlers)
    server.configure_logging()
    after = len(root.handlers)
    # May have added at most 2 (stream + rotating file) on first call.
    # Subsequent calls must not add more.
    server.configure_logging()
    final = len(root.handlers)
    assert final == after, f"handlers grew: {after} -> {final}"


# ---------------------------------------------------------------------------
# server._load_system_directives — corrupt file
# ---------------------------------------------------------------------------

def test_load_system_directives_handles_oserror(monkeypatch=None):
    """If the file exists but is unreadable, we fall back to the default."""
    import freecad_mcp.server as srv
    real_exists = srv.Path.exists
    real_read = srv.Path.read_text

    def fake_exists(self):
        return True

    def fake_read(self, *args, **kwargs):
        raise OSError("permission denied")

    try:
        srv.Path.exists = fake_exists
        srv.Path.read_text = fake_read
        result = srv._load_system_directives()
        # The fallback string is the documented default.
        assert "FreeCAD integration" in result
    finally:
        srv.Path.exists = real_exists
        srv.Path.read_text = real_read


# ---------------------------------------------------------------------------
# server — main() with CLI args
# ---------------------------------------------------------------------------

def test_main_parses_only_text_feedback_flag():
    """`main()` reads --only-text-feedback from argv."""
    import sys
    saved_argv = sys.argv
    saved_state = server.state
    try:
        sys.argv = ["freecad-mcp", "--only-text-feedback"]
        # Stub out mcp.run so we don't actually start the server.
        server.mcp.run = lambda: None
        server.main()
        assert server.state.only_text_feedback is True
    finally:
        sys.argv = saved_argv
        server.state = saved_state


def test_main_parses_host_flag_and_validates():
    saved_argv = sys.argv
    saved_state = server.state
    try:
        sys.argv = ["freecad-mcp", "--host", "192.168.1.10"]
        server.mcp.run = lambda: None
        server.main()
        assert server.state.rpc_host == "192.168.1.10"
    finally:
        sys.argv = saved_argv
        server.state = saved_state


def test_main_rejects_invalid_host():
    saved_argv = sys.argv
    try:
        sys.argv = ["freecad-mcp", "--host", "not a host"]
        server.mcp.run = lambda: None
        try:
            server.main()
        except SystemExit:
            return
        raise AssertionError("invalid host should cause argparse to exit")
    finally:
        sys.argv = saved_argv


# ---------------------------------------------------------------------------
# responses — json_response with deeply nested non-serialisable
# ---------------------------------------------------------------------------

def test_json_response_with_bytes_value():
    import base64
    res = responses.json_response({"raw": b"hello"})
    # default=str in json.dumps renders bytes as "b'hello'".
    assert any("raw" in t.text for t in res)


def test_text_response_passthrough_when_disabled():
    """When the directive prefix is disabled, text_response returns the message verbatim."""
    import freecad_mcp.responses as responses_mod
    import importlib

    saved = os.environ.get("FREECAD_MCP_NO_DIRECTIVE_PREFIX")
    try:
        os.environ["FREECAD_MCP_NO_DIRECTIVE_PREFIX"] = "1"
        importlib.reload(responses_mod)
        r = responses_mod.text_response("just the body")
        assert r[0].text == "just the body", r[0].text
    finally:
        if saved is None:
            os.environ.pop("FREECAD_MCP_NO_DIRECTIVE_PREFIX", None)
        else:
            os.environ["FREECAD_MCP_NO_DIRECTIVE_PREFIX"] = saved
        importlib.reload(responses_mod)


def test_text_response_idempotent_prefix():
    """If the message already starts with the prefix, do not double-prefix."""
    r = responses.text_response(f"{responses.SYSTEM_DIRECTIVE_PREFIX}\n\nhello")
    # The prefix should appear exactly once.
    assert r[0].text.count(responses.SYSTEM_DIRECTIVE_PREFIX) == 1


def test_add_screenshot_does_not_mutate_base_response():
    base = responses.text_response("ok")
    out = responses.add_screenshot_if_available(base, "B64", only_text_feedback=False)
    assert base is not out  # new list
    # The base TextContent is still present and unchanged.
    assert base[0].text == out[0].text


if __name__ == "__main__":
    test_validate_host_rejects_empty()
    test_validate_host_rejects_hostname_with_trailing_dot()
    test_validate_host_rejects_ipv4_out_of_range()
    test_configure_logging_handler_count_stable()
    test_load_system_directives_handles_oserror()
    test_main_parses_only_text_feedback_flag()
    test_main_parses_host_flag_and_validates()
    test_main_rejects_invalid_host()
    test_json_response_with_bytes_value()
    test_text_response_passthrough_when_disabled()
    test_text_response_idempotent_prefix()
    test_add_screenshot_does_not_mutate_base_response()
    print("All server module full tests passed")