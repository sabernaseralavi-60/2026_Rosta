"""تست سلامت — M0-03."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


async def test_health_is_public_and_cheap(client) -> None:  # type: ignore[no-untyped-def]
    """`/health` نباید به دیتابیس دست بزند — برای healthcheck داکر است."""
    response = await client.get("/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["environment"] == "test"


async def test_ready_reports_dependency_status(client) -> None:  # type: ignore[no-untyped-def]
    response = await client.get("/health/ready")
    assert response.status_code in (200, 503)
    assert "database" in response.json()["checks"]


async def test_health_is_excluded_from_openapi(app) -> None:  # type: ignore[no-untyped-def]
    """مسیرهای سلامت بخشی از قرارداد عمومی API نیستند."""
    assert not [p for p in app.openapi()["paths"] if p.startswith("/health")]


async def test_every_response_carries_a_trace_id(client) -> None:  # type: ignore[no-untyped-def]
    """NFR-16 — ردیابی از هدر ورودی تا پاسخ منتشر می‌شود."""
    given = "018f2a00-0000-7000-8000-00000000abcd"
    response = await client.get("/health", headers={"X-Trace-Id": given})
    assert response.headers["X-Trace-Id"] == given


async def test_invalid_trace_id_is_replaced_not_echoed(client) -> None:  # type: ignore[no-untyped-def]
    """شناسهٔ ورودی دلخواه نباید لاگ را آلوده کند."""
    response = await client.get("/health", headers={"X-Trace-Id": "'; DROP TABLE users--"})
    assert response.headers["X-Trace-Id"] != "'; DROP TABLE users--"
