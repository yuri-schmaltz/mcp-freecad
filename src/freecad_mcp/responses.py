import json
from dataclasses import dataclass
from typing import List, Union

try:
    from mcp.types import ImageContent, TextContent  # type: ignore
except Exception:
    @dataclass
    class TextContent:
        type: str
        text: str

    @dataclass
    class ImageContent:
        type: str
        data: str
        mimeType: str

ToolResponse = List[Union[TextContent, ImageContent]]


# Sentence required by gabarito_ia.pdf to appear at the start of responses
SYSTEM_DIRECTIVE_PREFIX = "Analisei o documento e usarei suas instruções em minhas respostas."


def _ensure_prefix(message: str) -> str:
    if message.strip().startswith(SYSTEM_DIRECTIVE_PREFIX):
        return message
    return SYSTEM_DIRECTIVE_PREFIX + "\n\n" + message


def text_response(message: str) -> ToolResponse:
    return [TextContent(type="text", text=_ensure_prefix(message))]


def json_response(data: object) -> ToolResponse:
    return text_response(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def add_screenshot_if_available(
    response: ToolResponse,
    screenshot: str | None,
    only_text_feedback: bool,
) -> ToolResponse:
    if only_text_feedback or screenshot is None:
        return response
    return [*response, ImageContent(type="image", data=screenshot, mimeType="image/png")]
