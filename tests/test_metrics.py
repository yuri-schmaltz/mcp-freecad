"""Unit tests for the Prometheus-style metrics registry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from freecad_mcp.metrics import (  # noqa: E402
    Counter,
    Gauge,
    Histogram,
    MetricsRegistry,
    format_prometheus,
)


# --- Counter -------------------------------------------------------------

def test_counter_increments():
    c = Counter("test_total", "test", labelnames=("tool",))
    c.inc("a")
    c.inc("a")
    c.inc("b", amount=5)
    assert c.value("a") == 2
    assert c.value("b") == 5
    assert c.value("c") == 0


def test_counter_rejects_negative():
    c = Counter("test_total", "test")
    try:
        c.inc(amount=-1)
    except ValueError:
        return
    raise AssertionError("expected ValueError on negative inc")


def test_counter_label_count_mismatch():
    c = Counter("test_total", "test", labelnames=("a", "b"))
    try:
        c.inc("only-one")
    except ValueError:
        return
    raise AssertionError("expected ValueError on label mismatch")


# --- Histogram -----------------------------------------------------------

def test_histogram_observe_buckets():
    h = Histogram("test_seconds", "test", labelnames=("tool",), buckets=(0.1, 0.5, 1.0))
    h.observe(0.05, "create_object")  # le_0.1
    h.observe(0.3, "create_object")   # le_0.5
    h.observe(0.8, "create_object")   # le_1.0
    h.observe(2.0, "create_object")   # le_inf
    snap = h.snapshot("create_object")
    assert snap["count"] == 4
    assert snap["sum"] == 0.05 + 0.3 + 0.8 + 2.0
    assert snap["le_0.1"] == 1
    assert snap["le_0.5"] == 2
    assert snap["le_1.0"] == 3
    assert snap["le_inf"] == 4


def test_histogram_rejects_bad_buckets():
    try:
        Histogram("x", "x", buckets=(0, 1, 2))
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-positive bucket")
    try:
        Histogram("x", "x", buckets=(1, 0.5, 2))
    except ValueError:
        return
    raise AssertionError("expected ValueError for non-monotonic bucket")


# --- Gauge ---------------------------------------------------------------

def test_gauge_set_and_read():
    g = Gauge("test_state", "test")
    g.set(42)
    assert g.value() == 42
    g.set(7.5)
    assert g.value() == 7.5


# --- Registry + Prometheus output ---------------------------------------

def test_registry_has_default_metrics():
    r = MetricsRegistry()
    assert r.tool_calls is not None
    assert r.tool_duration is not None
    assert r.validation_failures is not None
    assert r.circuit_state is not None
    assert r.circuit_short_circuits is not None
    assert r.uptime_seconds is not None


def test_registry_records_calls():
    r = MetricsRegistry()
    r.tool_calls.inc("create_object", "success")
    r.tool_calls.inc("create_object", "success")
    r.tool_calls.inc("create_object", "error")
    r.tool_duration.observe(0.123, "create_object")
    r.validation_failures.inc("create_object")
    snap = r.as_dict()
    assert snap["tool_calls"][("create_object|success" if False else "create_object|success")] == 2 or \
        snap["tool_calls"].get("create_object|success") == 2
    assert snap["tool_calls"].get("create_object|error") == 1
    assert snap["validation_failures"].get("create_object") == 1


def test_format_prometheus_contains_counters_and_histogram():
    r = MetricsRegistry()
    r.tool_calls.inc("create_object", "success")
    r.tool_calls.inc("create_object", "error")
    r.tool_duration.observe(0.5, "create_object")
    out = format_prometheus(r)
    # Header for the tool_calls counter
    assert "freecad_mcp_tool_calls_total" in out
    assert 'tool="create_object"' in out
    assert 'status="success"' in out
    # Histogram has bucket and sum lines
    assert "freecad_mcp_tool_duration_seconds_bucket" in out
    assert "freecad_mcp_tool_duration_seconds_sum" in out
    assert "freecad_mcp_tool_duration_seconds_count" in out
    # Gauges
    assert "freecad_mcp_circuit_state" in out
    assert "freecad_mcp_uptime_seconds" in out


def test_format_prometheus_uses_cumulative_buckets():
    """In Prometheus, bucket counts are cumulative (le_1.0 >= le_0.5)."""
    import re as _re
    r = MetricsRegistry()
    r.tool_duration.observe(0.05, "x")
    r.tool_duration.observe(0.3, "x")
    r.tool_duration.observe(2.0, "x")
    out = format_prometheus(r)
    # Parse the bucket lines for the 'x' tool and ensure cumulativity.
    bucket_counts: dict[float, int] = {}
    for line in out.splitlines():
        if 'freecad_mcp_tool_duration_seconds_bucket' not in line:
            continue
        if 'tool="x"' not in line:
            continue
        if 'le="+Inf"' in line:
            continue
        # Format: ``name{tool="x",le="0.5"} 2``
        m = _re.search(r'le="([^"]+)"\}\s+(\d+)', line)
        assert m is not None, line
        le = float(m.group(1))
        count = int(m.group(2))
        bucket_counts[le] = count
    # Bucket values must be non-decreasing.
    le_values = sorted(bucket_counts)
    counts = [bucket_counts[le] for le in le_values]
    assert counts == sorted(counts), f"non-cumulative buckets: {bucket_counts}"


def test_health_check_operation_includes_metrics(monkeypatch):
    """The health_check tool should expose the metrics block in JSON."""
    from freecad_mcp.operations import core as ops

    class _FakeConn:
        def health_check(self_inner):
            return {"success": True, "uptime_seconds": 1.0, "rpc_server_running": True}

        def breaker_metrics(self_inner):
            return {
                "state": "closed",
                "consecutive_failures": 0,
                "threshold": 3,
                "total_calls": 0,
                "total_failures": 0,
                "total_short_circuits": 0,
            }

    r = MetricsRegistry()
    r.tool_calls.inc("create_object", "success")
    result = ops.health_check_operation(_FakeConn(), r)
    import json as _json
    payload = _json.loads(result[0].text)
    assert "circuit_breaker" in payload
    assert "metrics" in payload
    assert payload["circuit_breaker"]["state"] == "closed"
    assert payload["metrics"]["tool_calls"].get("create_object|success") == 1


def test_health_check_circuit_short_circuits_is_absolute(monkeypatch):
    """v0.4.0 fix: the metric must be ``set`` (not ``inc``) from the breaker's
    absolute counter. Two consecutive health_checks with the same breaker
    state must yield the same metric value, not a doubled one.
    """
    from freecad_mcp.operations import core as ops

    class _FakeConn:
        def __init__(self):
            self.health_check_calls = 0

        def health_check(self_inner):
            self_inner.health_check_calls += 1
            return {"success": True, "uptime_seconds": 1.0, "rpc_server_running": True}

        def breaker_metrics(self_inner):
            # Absolute counts — should NOT grow with the number of health_check calls.
            return {
                "state": "closed",
                "consecutive_failures": 0,
                "threshold": 3,
                "total_calls": 100,
                "total_failures": 5,
                "total_short_circuits": 7,
            }

    r = MetricsRegistry()
    fake = _FakeConn()
    ops.health_check_operation(fake, r)
    first = r.circuit_short_circuits.value()
    assert first == 7.0, f"expected 7, got {first}"

    ops.health_check_operation(fake, r)
    second = r.circuit_short_circuits.value()
    assert second == 7.0, f"BUG: counter doubled on second call: {second}"

    ops.health_check_operation(fake, r)
    third = r.circuit_short_circuits.value()
    assert third == 7.0, f"BUG: counter tripled on third call: {third}"


if __name__ == "__main__":
    print("Run with pytest; direct invocation is not supported.")
