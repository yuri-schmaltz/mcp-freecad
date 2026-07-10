from dataclasses import dataclass, field

from .freecad_client import FreeCADConnection
from .metrics import MetricsRegistry


@dataclass
class ServerState:
    only_text_feedback: bool = False
    rpc_host: str = "localhost"
    freecad_connection: FreeCADConnection | None = None
    # v0.4.0 — Prometheus-style metrics registry. One per process;
    # populated by tool wrappers and exposed via health_check.
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)
