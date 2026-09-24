"""ابزار کار پس‌زمینه — M7-17، NFR-15."""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import REGISTRY

from silp.core.metrics import timed_job


def _value(name: str, task: str) -> float:
    return REGISTRY.get_sample_value(name, {"task": task}) or 0.0


async def test_success_records_duration_and_timestamp() -> None:
    @timed_job
    async def unit_ok_job(ctx: dict[str, Any]) -> int:
        return 7

    before = _value("background_job_duration_seconds_count", "unit_ok_job")
    assert await unit_ok_job({}) == 7
    assert _value("background_job_duration_seconds_count", "unit_ok_job") == before + 1
    assert _value("silp_background_job_last_success_timestamp_seconds", "unit_ok_job") > 0
    assert _value("background_job_failures_total", "unit_ok_job") == 0


async def test_failure_is_counted_and_reraised() -> None:
    """شکست بلعیده نمی‌شود: ARQ باید تلاش دوباره را خودش ببیند."""

    @timed_job
    async def unit_bad_job(ctx: dict[str, Any]) -> None:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await unit_bad_job({})
    assert _value("background_job_failures_total", "unit_bad_job") == 1
    assert _value("silp_background_job_last_success_timestamp_seconds", "unit_bad_job") == 0


def test_wrapper_keeps_the_job_name() -> None:
    """ARQ کار را با نام تابع می‌شناسد؛ نام عوض شود، کارهای صف گم می‌شوند."""
    from silp.workers.settings import WorkerSettings

    names = {fn.__name__ for fn in WorkerSettings.functions}
    assert "close_expired_attempts" in names
    assert "dispatch_outbox" in names
