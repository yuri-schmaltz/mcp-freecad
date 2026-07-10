"""Property-based fuzzing with Hypothesis.

These tests generate random inputs and assert invariants that must
hold across all possible inputs. They are slower than the per-
example tests (Hypothesis explores many shrinking paths per run)
but catch classes of bugs that hand-picked examples miss:

* Crashes on weird Unicode (right-to-left override, null bytes,
  surrogate pairs, BMP edge cases).
* Off-by-one in pattern matching.
* Numeric overflow / wraparound in metrics.
* Counter state-machine violations (e.g. ``set`` not actually
  replacing the prior value).

Each test is annotated with the *invariant* it asserts, so a
failure tells you which property was violated.

The fuzzer is conservative: examples are small, ``max_examples=50``
keeps the suite fast enough for CI, and the ``deadline=None`` lifts
the per-example deadline because some regex evaluations on huge
inputs would otherwise be flaky.

Run with::

    .venv/bin/python -m pytest tests/test_fuzz_properties.py -v

Or, for a longer exploratory run::

    HYPOTHESIS_PROFILE=ci .venv/bin/python -m pytest tests/test_fuzz_properties.py
"""
from __future__ import annotations

import string
import sys
from pathlib import Path

# Make the in-tree src/ importable without an editable install
# (matches the pattern used by every other test in this directory).
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from hypothesis import HealthCheck, given, settings, assume, strategies as st

# --- Imports guarded so the test file is importable even if the addon
# path is not in PYTHONPATH. ----------------------------------------------------
try:
    from freecad_mcp.guidelines import (
        _DANGEROUS_PATTERNS,
        _EXTRA_DANGEROUS,
        check_code_conflict,
        scan_dangerous_tokens,
    )
except Exception:  # pragma: no cover - import-time guard
    _DANGEROUS_PATTERNS = ()
    _EXTRA_DANGEROUS = ()
    check_code_conflict = None  # type: ignore[assignment]
    scan_dangerous_tokens = None  # type: ignore[assignment]

try:
    from freecad_mcp.metrics import Counter
except Exception:  # pragma: no cover
    Counter = None  # type: ignore[assignment]


# --- Strategies ---------------------------------------------------------------

# Anything Hypothesis can pull out of a "small Python snippet" generator.
# We don't try to generate syntactically valid Python (that is intractable);
# the fuzz is about invariants like "no crash" and "set replaces value".
_short_strings = st.text(
    alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Pc", "Pd", "Po", "Ps", "Pe", "Zs"),
        blacklist_characters="\x00",
    ),
    min_size=0,
    max_size=200,
)

_unicode_strings = st.text(min_size=0, max_size=100)

_benign_python = st.sampled_from([
    "box = doc.addObject('Part::Box', 'Box')",
    "box.Length = 10.0",
    "box.Width = 5.0",
    "doc.recompute()",
    "import FreeCAD\ndoc = FreeCAD.newDocument('X')",
    "FreeCAD.Console.PrintMessage('hello')",
    "for i in range(10):\n    print(i)",
    "result = a + b * 3.14",
    "x = [i**2 for i in range(10)]",
    "def f(x):\n    return x * 2",
    "if True:\n    pass",
    "# a comment\nx = 1",
    'name = "box-01"',
    "1 + 2 + 3 + 4",
    "",
    "    ",  # whitespace only
    "\n\n\n",
])

# Inputs explicitly engineered to confuse pattern matchers.
_weird_strings = st.sampled_from([
    "\u202Eevil.exe",                # right-to-left override
    "import\x00os",                   # embedded null
    "GETATTR" + "".join(["_"] * 5) + "BUILTINS",  # underscore spam
    "compile" + " " * 100 + "code",
    "__class__" * 50,
    "getattr(__builtins__, 'ev" + chr(0xAD) + "al')",  # soft hyphen inside
    "\n".join(["__import__('os')"] * 20),
    "pickle" + "\n" + "loads",
    "exec" * 100,
    "eval(" + "a" * 1000 + ")",
])


# --- Guidelines fuzzing -------------------------------------------------------

pytestmark = [
    pytest.mark.skipif(scan_dangerous_tokens is None, reason="guidelines import failed"),
    # Fuzz tests are slower; allow them to run without hitting the global
    # deadline.
]


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_short_strings)
def test_scan_dangerous_tokens_never_crashes(text: str) -> None:
    """Invariant: scan_dangerous_tokens is total \u2014 it never raises.

    The function is called on untrusted input (any code string the
    LLM proposes), so it must survive arbitrary text without
    throwing.
    """
    result = scan_dangerous_tokens(text)
    assert isinstance(result, list)
    # Every match must be a Pattern that exists in the registered
    # pattern set \u2014 we cannot leak internal references that
    # weren't declared.
    registered = set(_DANGEROUS_PATTERNS) | set(_EXTRA_DANGEROUS)
    for pat in result:
        assert pat in registered


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_unicode_strings)
def test_scan_dangerous_tokens_unicode_safe(text: str) -> None:
    """Invariant: Unicode (including right-to-left, soft hyphens, etc.)
    does not crash the blocklist and does not produce ghost matches.

    The blocklist operates on Python source; we still want it to be
    safe to call on arbitrary Unicode (e.g. on error messages that
    include user-provided strings).
    """
    result = scan_dangerous_tokens(text)
    assert isinstance(result, list)
    for pat in result:
        # If a pattern is reported as matching, the pattern's
        # .search() must agree when called again on the same input.
        # This catches caches that key on id() or similar.
        assert pat.search(text) is not None


@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(text=_short_strings)
def test_check_code_conflict_total_function(text: str) -> None:
    """Invariant: check_code_conflict is a total function returning
    ``(bool, str)`` for any string input, including the empty string.

    A violation here would let untrusted input cause an unhandled
    exception on the server side, which is a security finding.
    """
    blocked, msg = check_code_conflict(text)
    assert isinstance(blocked, bool)
    assert isinstance(msg, str)
    if not blocked:
        assert msg == ""
    if blocked:
        assert msg  # non-empty when blocked


@given(code=_benign_python)
def test_benign_python_never_blocked(code: str) -> None:
    """Invariant: common FreeCAD Python snippets are NEVER blocked.

    The blocklist is tuned for *dangerous* patterns; false positives
    on ordinary FreeCAD scripting would degrade the user experience
    to the point where users disable the blocklist entirely.
    """
    blocked, _msg = check_code_conflict(code)
    assert blocked is False, f"benign snippet was blocked: {code!r}"


@given(code=_weird_strings)
def test_weird_inputs_do_not_crash(code: str) -> None:
    """Invariant: weird/unusual inputs do not crash the blocklist.

    The blocklist must be robust to:
    * Right-to-left override characters (the snippet still says what
      the user typed, but a confused regex engine might not).
    * Embedded null bytes.
    * Excessive repetition.
    * Soft hyphens inside identifiers.

    We don't assert what the verdict IS (the blocklist is allowed to
    flag weird-looking input as suspicious), only that the call
    returns cleanly.
    """
    blocked, msg = check_code_conflict(code)
    assert isinstance(blocked, bool)
    assert isinstance(msg, str)


# --- Counter fuzzing ----------------------------------------------------------

counter_required = pytest.mark.skipif(Counter is None, reason="metrics import failed")


@counter_required
@settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    n=st.integers(min_value=0, max_value=10_000),
    set_value=st.floats(min_value=0, max_value=1e9, allow_nan=False, allow_infinity=False),
    label=st.sampled_from(["a", "b", "c", "", "label with spaces", "x" * 50]),
)
def test_counter_set_replaces_value(n: int, set_value: float, label: str) -> None:
    """Invariant: ``Counter.set(v)`` makes ``.value() == v`` regardless
    of prior ``.inc()`` calls.

    This is the v0.4.0 HIGH bug we previously fixed: ``set`` was
    *adding* to the prior value rather than replacing it. The fuzz
    test exercises many ``inc``/``set`` interleavings to make sure
    no future regression slips in.
    """
    counter = Counter("test", "Test counter", labelnames=("label",))
    for _ in range(n):
        counter.inc(label, amount=1.0)
    counter.set(set_value, label)
    assert counter.value(label) == set_value


@counter_required
@given(
    incs=st.lists(
        st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
        min_size=0,
        max_size=100,
    ),
    label=st.sampled_from(["a", "b", "c"]),
)
def test_counter_inc_accumulates(incs: list[float], label: str) -> None:
    """Invariant: ``Counter.inc()`` is additive; the final value
    equals the sum of all increments (within float precision).

    We tolerate 1e-3 absolute error because float addition is not
    associative, but the sum of N copies of a value should converge
    to N * value modulo float rounding.
    """
    counter = Counter("test", "Test counter", labelnames=("label",))
    expected = 0.0
    for v in incs:
        counter.inc(label, amount=v)
        expected += v
    actual = counter.value(label)
    if expected == 0.0:
        assert actual == 0.0
    else:
        # Relative error bound for adding 100 floats \u2264 ~1e-12.
        assert abs(actual - expected) <= max(1e-3, abs(expected) * 1e-9), (
            f"inc accumulated {actual!r}, expected {expected!r} "
            f"(input was {incs!r})"
        )


@counter_required
@given(
    incs=st.integers(min_value=0, max_value=50),
    sets=st.integers(min_value=1, max_value=50),  # at least one set, else test is vacuous
    set_value=st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
)
def test_counter_set_is_idempotent(incs: int, sets: int, set_value: float) -> None:
    """Invariant: Calling ``set(v)`` multiple times in a row leaves
    the counter at ``v``; the last set wins.
    """
    counter = Counter("test", "Test counter")
    for _ in range(incs):
        counter.inc()
    for _ in range(sets):
        counter.set(set_value)
    assert counter.value() == set_value


@counter_required
@given(value=st.floats(allow_nan=False, allow_infinity=False, min_value=0, max_value=1e9))
def test_counter_set_zero_is_not_replaced_by_later_inc(value: float) -> None:
    """Invariant: After ``set(0)``, the next ``inc(5)`` brings the
    counter to exactly 5.0 \u2014 not to 0 + 5 = 5 (lucky), not to
    0 * 5 = 0 (broken).
    """
    counter = Counter("test", "Test counter")
    counter.set(value)
    counter.inc(amount=5.0)
    assert counter.value() == value + 5.0
