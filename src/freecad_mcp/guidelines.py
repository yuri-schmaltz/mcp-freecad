"""Prompt- and code-conflict guards for the MCP layer.

Three independent checks live here, each scoped to the field it actually
applies to:

* :func:`check_code_conflict` — runs on **executable** strings only
  (``code`` parameter of :func:`execute_code`). Detects dangerous builtins
  and OS calls via word-bounded regexes (so ``evaluate`` does NOT match
  ``eval`` and ``os . system`` still matches ``os.system``).
* :func:`check_prompt_conflict` — runs on free-form **prompt text**
  (agreement-trap phrases asking the model to bypass its own safeguards).
* :func:`check_path_conflict` — runs on **filesystem path strings**
  (defence in depth on top of :func:`parts_library._safe_resolve`).

The previous implementation conflated these three scopes and used
substring matching, which caused both false positives (legitimate
object names like ``"evaluation panel"``) and trivial bypasses
(``ev al(``, ``\\x65val(``). See ``docs/IMPROVEMENT_PLAN.md`` items C3
and C4 for the rationale.

Operators can extend the dangerous-token list at runtime via the
``FREECAD_MCP_BLOCKED_PATTERNS`` env var (comma-separated regexes).
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("FreeCADMCPguidelines")


# ---------------------------------------------------------------------------
# Dangerous patterns (applied to executable code / path strings)
# ---------------------------------------------------------------------------

# Each entry is a precompiled regex; they use \b word boundaries and allow
# optional whitespace between identifier parts so trivial bypasses like
# 'os . system' or 'subprocess . run' still match.
_DANGEROUS_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Builtin exec/eval — require the opening '(' to reduce false positives
    # on words like "evaluate", "execution", "executable".
    re.compile(r"\beval\s*\(", re.IGNORECASE),
    re.compile(r"\bexec\s*\(", re.IGNORECASE),
    # os.system / os.popen / os.exec* family.
    re.compile(r"\bos\s*\.\s*system\s*\(", re.IGNORECASE),
    re.compile(r"\bos\s*\.\s*popen\s*\(", re.IGNORECASE),
    re.compile(r"\bos\s*\.\s*exec[lv]p?\s*\(", re.IGNORECASE),
    # subprocess.<call>() — the bare 'subprocess' import is also flagged
    # because importing it without using it is rarely legitimate in this
    # context, and any use site calls one of these functions anyway.
    re.compile(r"\bsubprocess\s*\.\s*(?:run|call|check_call|check_output|Popen)\s*\(", re.IGNORECASE),
    re.compile(r"^\s*import\s+subprocess\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^\s*from\s+subprocess\b", re.IGNORECASE | re.MULTILINE),
    # Shell-level rm -rf / — requires a path starting with '/' to avoid
    # matching e.g. "rm -rf ./build" (which is a perfectly normal build
    # cleanup operation). Flag combinations like -rf, -fr, -Rf, -Rfv all
    # match because the flag char-class is [a-zA-Z]*.
    re.compile(r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+/", re.IGNORECASE),
    re.compile(r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+-[a-zA-Z]*\s+/", re.IGNORECASE),
    # Host shutdown / reboot.
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\breboot\b", re.IGNORECASE),
)


def _load_extra_patterns() -> tuple[re.Pattern[str], ...]:
    """Read ``FREECAD_MCP_BLOCKED_PATTERNS`` (comma-separated regexes)."""
    raw = os.environ.get("FREECAD_MCP_BLOCKED_PATTERNS", "").strip()
    if not raw:
        return ()
    out: list[re.Pattern[str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            out.append(re.compile(entry, re.IGNORECASE))
        except re.error as e:
            logger.warning("Ignoring invalid blocked pattern %r: %s", entry, e)
    return tuple(out)


_EXTRA_DANGEROUS: tuple[re.Pattern[str], ...] = _load_extra_patterns()


# ---------------------------------------------------------------------------
# Agreement-trap patterns (applied to prompt text only)
# ---------------------------------------------------------------------------

_AGREEMENT_TRAP_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdo\s+exactly\s+as\s+i\s+say\b", re.IGNORECASE),
    re.compile(r"\bignore\s+(?:safety|safeguards?|guidelines?|rules?|instructions?)\b", re.IGNORECASE),
    re.compile(r"\bdon'?t\s+question\b", re.IGNORECASE),
    re.compile(r"\bno\s+questions?\s+asked\b", re.IGNORECASE),
    re.compile(r"\bbypass\s+(?:the\s+)?(?:safety|safeguards?|filters?|checks?)\b", re.IGNORECASE),
    re.compile(r"\bdisable\s+(?:the\s+)?(?:safety|safeguards?|filters?|checks?)\b", re.IGNORECASE),
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _match_any(
    patterns: tuple[re.Pattern[str], ...], text: str
) -> re.Pattern[str] | None:
    for pat in patterns:
        if pat.search(text):
            return pat
    return None


def check_code_conflict(code: str) -> tuple[bool, str]:
    """Check an executable string (Python code, shell snippet) for dangerous calls.

    Returns ``(conflict, message)``. Safe strings return ``(False, "")``.
    """
    if not code:
        return False, ""

    matched = _match_any(_DANGEROUS_PATTERNS, code)
    if matched is None:
        matched = _match_any(_EXTRA_DANGEROUS, code)
    if matched is None:
        return False, ""

    pattern = matched.pattern
    msg = (
        f"Refusing to execute code containing pattern '{pattern}'. "
        "Provide a safer, well-scoped snippet or describe the high-level "
        "change you want; a secure implementation will be proposed."
    )
    logger.warning("code blocked by guidelines (pattern=%r). excerpt=%r", pattern, code[:200])
    return True, msg


def check_prompt_conflict(prompt: str) -> tuple[bool, str]:
    """Check free-form prompt text for agreement-trap phrases.

    Use this for user-supplied text that the LLM will interpret; use
    :func:`check_code_conflict` for strings that will be executed by
    FreeCAD. The two checks do not overlap on purpose.
    """
    if not prompt:
        return False, ""

    matched = _match_any(_AGREEMENT_TRAP_PATTERNS, prompt)
    if matched is None:
        return False, ""

    pattern = matched.pattern
    msg = (
        "Request asks to bypass safeguards or unquestioningly follow "
        "instructions; will not comply as-is. Provide a revised request "
        "that does not ask the assistant to disable its own checks."
    )
    logger.warning("prompt blocked by guidelines (pattern=%r). excerpt=%r", pattern, prompt[:200])
    return True, msg


def check_path_conflict(path: str) -> tuple[bool, str]:
    """Defence-in-depth check on a filesystem path string.

    The authoritative validation is :func:`parts_library._safe_resolve`
    (which uses realpath comparisons). This function exists to short-circuit
    obviously dangerous strings *before* they hit FreeCAD's mergeProject and
    to provide a uniform refusal message at the MCP layer.
    """
    if not path:
        return False, ""

    if os.path.isabs(path):
        return True, f"Path must be relative, got absolute path: {path!r}"

    # Normalise and reject any '..' segment.
    normalised = os.path.normpath(path)
    if normalised.startswith("..") or os.path.isabs(normalised):
        return True, f"Path escapes the parts library: {path!r}"

    return False, ""


__all__ = [
    "check_code_conflict",
    "check_prompt_conflict",
    "check_path_conflict",
]
