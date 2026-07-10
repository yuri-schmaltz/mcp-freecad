"""JSON log formatter for production log shippers.

A drop-in replacement for ``logging.Formatter`` that emits each
record as a single line of JSON. Standard fields:

* ``ts`` \u2014 ISO 8601 UTC timestamp with millisecond precision.
* ``level`` \u2014 log level (DEBUG/INFO/WARNING/...).
* ``logger`` \u2014 logger name.
* ``msg`` \u2014 formatted log message.

Any ``extra={...}`` keywords passed to the logging call are merged
into the top-level JSON object, so ``logger.info("opened", extra={"port": 9875})``
emits ``{"msg": "opened", "port": 9875, ...}``.

``exc_info`` (when present) is rendered to a ``"exc_info"`` field as
a string. ``args`` are rendered with the standard ``msg % args``
substitution before serialisation.
"""
from __future__ import annotations

import datetime
import json
import logging
from collections.abc import MutableMapping
from typing import Any

# Fields that the LogRecord sets itself and that we copy verbatim.
_STANDARD_RECORD_FIELDS: frozenset[str] = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "asctime",
})


class JsonLogFormatter(logging.Formatter):
    """Emit each LogRecord as a single JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.datetime.fromtimestamp(
                record.created, tz=datetime.UTC
            ).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Merge any extras the caller passed via ``extra=``.
        # These live on the record under names not in the standard set
        # and not starting with the leading-underscore convention
        # used internally by logging (e.g. ``_style``).
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_FIELDS or key.startswith("_"):
                continue
            if key in payload:
                # Don't let user-supplied extras shadow our standard fields.
                continue
            payload[key] = _safe_for_json(value)

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, ensure_ascii=False, default=_safe_for_json)


def _safe_for_json(value: Any) -> Any:
    """Make *value* JSON-serialisable without raising."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_for_json(v) for v in value]
    if isinstance(value, MutableMapping):
        return {str(k): _safe_for_json(v) for k, v in value.items()}
    return repr(value)


__all__ = ["JsonLogFormatter"]
