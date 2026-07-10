"""Unit tests for the remote-connections security gate.

The gate is the v0.4.0 line of defence against accidentally exposing
the FreeCAD RPC server (and therefore ``execute_code`` = arbitrary
Python) to the local network. It is pure-Python so it can be tested
without FreeCAD.
"""
import sys
from pathlib import Path

# The gate is in the addon, not src/; import via the package path.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "addon" / "FreeCADMCP" / "rpc_server"))

import _security_gate as gate  # noqa: E402


def test_localhost_is_always_allowed():
    for h in ("localhost", "127.0.0.1", "::1"):
        allowed, missing = gate.can_start_remote_server(h, env={})
        assert allowed is True, h
        assert missing == []


def test_remote_host_without_env_is_refused():
    allowed, missing = gate.can_start_remote_server("0.0.0.0", env={})
    assert allowed is False
    assert "FREECAD_MCP_TLS_CERT" in missing
    assert "FREECAD_MCP_TLS_KEY" in missing
    assert "FREECAD_MCP_AUTH_TOKEN" in missing


def test_remote_host_with_all_env_is_allowed():
    env = {
        "FREECAD_MCP_TLS_CERT": "/etc/ssl/cert.pem",
        "FREECAD_MCP_TLS_KEY": "/etc/ssl/key.pem",
        "FREECAD_MCP_AUTH_TOKEN": "s3cret-token",
    }
    allowed, missing = gate.can_start_remote_server("0.0.0.0", env=env)
    assert allowed is True
    assert missing == []


def test_empty_string_env_is_treated_as_missing():
    """A whitespace-only env var is the same as unset \u2014 an attacker
    could otherwise set ``FREECAD_MCP_TLS_CERT=' '`` to bypass the gate.
    """
    env = {
        "FREECAD_MCP_TLS_CERT": "",
        "FREECAD_MCP_TLS_KEY": "   ",
        "FREECAD_MCP_AUTH_TOKEN": "valid",
    }
    allowed, missing = gate.can_start_remote_server("0.0.0.0", env=env)
    assert allowed is False
    assert "FREECAD_MCP_TLS_CERT" in missing
    assert "FREECAD_MCP_TLS_KEY" in missing
    assert "FREECAD_MCP_AUTH_TOKEN" not in missing


def test_partial_env_lists_exact_missing():
    env = {"FREECAD_MCP_TLS_CERT": "/etc/cert.pem"}
    allowed, missing = gate.can_start_remote_server("0.0.0.0", env=env)
    assert allowed is False
    assert "FREECAD_MCP_TLS_CERT" not in missing
    assert sorted(missing) == ["FREECAD_MCP_AUTH_TOKEN", "FREECAD_MCP_TLS_KEY"]


def test_refusal_message_mentions_each_missing_var():
    msg = gate.format_refusal_message(["FREECAD_MCP_TLS_CERT", "FREECAD_MCP_AUTH_TOKEN"])
    assert "FREECAD_MCP_TLS_CERT" in msg
    assert "FREECAD_MCP_AUTH_TOKEN" in msg
    assert "SECURITY.md" in msg


def test_refusal_message_empty_for_empty_list():
    assert gate.format_refusal_message([]) == ""


def test_gate_uses_os_environ_by_default(monkeypatch):
    """When no env dict is passed, the gate must read os.environ.

    This is the behaviour the addon code relies on at start time.
    """
    monkeypatch.delenv("FREECAD_MCP_TLS_CERT", raising=False)
    monkeypatch.delenv("FREECAD_MCP_TLS_KEY", raising=False)
    monkeypatch.delenv("FREECAD_MCP_AUTH_TOKEN", raising=False)
    allowed, missing = gate.can_start_remote_server("0.0.0.0")
    assert allowed is False
    assert len(missing) == 3


def test_gate_does_not_mutate_passed_env():
    """A copy is taken / the env is read-only \u2014 the gate must never
    insert default values or sanitise the caller's dict.
    """
    env = {"FREECAD_MCP_AUTH_TOKEN": "abc"}
    gate.can_start_remote_server("0.0.0.0", env=env)
    assert env == {"FREECAD_MCP_AUTH_TOKEN": "abc"}


if __name__ == "__main__":
    print("Run with pytest; direct invocation is not supported.")
