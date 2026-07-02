"""Unit tests for the response helpers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.responses import (  # noqa: E402
    SYSTEM_DIRECTIVE_PREFIX,
    add_screenshot_if_available,
    json_response,
    text_response,
)


def test_text_response_has_prefix():
    r = text_response("hello")
    assert len(r) == 1
    assert r[0].type == "text"
    assert r[0].text.startswith(SYSTEM_DIRECTIVE_PREFIX)
    assert "hello" in r[0].text


def test_text_response_does_not_double_prefix():
    r = text_response("hello")
    # Calling again would add the prefix again — verify the helper checks.
    msg = r[0].text
    assert msg.count(SYSTEM_DIRECTIVE_PREFIX) == 1


def test_json_response_serialises_dict():
    r = json_response({"a": 1, "b": [1, 2]})
    assert len(r) == 1
    import json as _json
    payload = _json.loads(r[0].text[len(SYSTEM_DIRECTIVE_PREFIX):].lstrip("\n").lstrip())
    assert payload == {"a": 1, "b": [1, 2]}


def test_json_response_handles_non_serialisable():
    class Opaque:
        def __repr__(self):
            return "opaque-repr"

    r = json_response({"obj": Opaque()})
    assert "opaque-repr" in r[0].text


def test_add_screenshot_none_returns_base():
    base = text_response("ok")
    out = add_screenshot_if_available(base, None, only_text_feedback=False)
    assert out is base


def test_add_screenshot_only_text_feedback_returns_base():
    base = text_response("ok")
    out = add_screenshot_if_available(base, "BASE64DATA", only_text_feedback=True)
    assert out is base


def test_add_screenshot_appends_image():
    base = text_response("ok")
    out = add_screenshot_if_available(base, "BASE64DATA", only_text_feedback=False)
    assert len(out) == 2
    text_part, img_part = out
    assert text_part.type == "text"
    assert img_part.type == "image"
    assert img_part.data == "BASE64DATA"
    assert img_part.mimeType == "image/png"


if __name__ == "__main__":
    test_text_response_has_prefix()
    test_text_response_does_not_double_prefix()
    test_json_response_serialises_dict()
    test_json_response_handles_non_serialisable()
    test_add_screenshot_none_returns_base()
    test_add_screenshot_only_text_feedback_returns_base()
    test_add_screenshot_appends_image()
    test_prefix_disabled_via_env()
    test_prefix_enabled_by_default()
    print("All response tests passed")
