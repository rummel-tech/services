"""Lightweight metrics shim for tests/dev to avoid optional deps.
Delegates to core.metrics if available; otherwise provides no-op counters/gauges.
"""
from typing import Any

try:
    from core.metrics import *  # type: ignore
except Exception:  # pragma: no cover - fallback when prometheus not installed
    import time

    class _NoopCounter:
        def labels(self, **kwargs: Any):
            return self

        def inc(self, amount: float = 1.0):
            return None

        def dec(self, amount: float = 1.0):
            return None

        def observe(self, value: float):
            return None

    REQUESTS_IN_PROGRESS = _NoopCounter()

    def start_timer() -> float:
        return time.time()

    def observe_request(method: str, path: str, status_code: int, start_time: float) -> None:
        return None

    def record_domain_event(event: str, **kwargs: Any) -> None:
        return None

    def record_error(event: str, **kwargs: Any) -> None:
        return None

    def record_cache_operation(kind: str) -> None:
        return None
