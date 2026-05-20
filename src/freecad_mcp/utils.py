from typing import Callable, Any
import logging
from functools import wraps

try:
    # Import here to avoid circular imports when running tests without full deps
    from .responses import text_response  # type: ignore
except Exception:
    def text_response(message: str):
        return [{"type": "text", "text": message}]

logger = logging.getLogger("FreeCADMCPutils")


def safe_operation(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to centralize exception handling for operations.

    On exception, logs the error and returns a user-friendly `text_response`.
    """

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.exception("Unhandled exception in %s", fn.__name__)
            try:
                return text_response(f"Internal server error in operation '{fn.__name__}': {e}")
            except Exception:
                # Fallback minimal response if text_response is unavailable
                return [{"type": "text", "text": f"Internal error: {e}"}]

    return wrapper
