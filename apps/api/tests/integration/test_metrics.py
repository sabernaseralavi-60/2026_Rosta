"""معیارهای Prometheus — NFR-14، M7-17."""

from __future__ import annotations

import uuid

import pytest

from silp.domain.notifications.catalog import EXTERNAL_CHANNELS

pytestmark = pytest.mark.integration


async def test_metrics_expose_database_and_http_series(client) -> None:  # type: ignore[no-untyped-def]
    await client.get("/api/v1/taxonomy/skills")
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text

    assert "silp_metrics_scrape_errors 0.0" in body
    assert "silp_users_registered_total" in body
    assert "silp_db_max_connections" in body
    assert 'route="/api/v1/taxonomy/skills"' in body


async def test_every_outbox_pair_has_a_series_even_at_zero(client) -> None:  # type: ignore[no-untyped-def]
    """هشدار «بیش از ۱۰ DEAD در ساعت» با delta() کار می‌کند؛ سری‌ای که تازه
    ظاهر شود delta ندارد، پس صفر هم باید سری داشته باشد."""
    body = (await client.get("/metrics")).text
    for channel in EXTERNAL_CHANNELS:
        assert f'outbox_queue_depth{{channel="{channel}",status="DEAD"}}' in body


async def test_route_label_is_the_template_not_the_raw_path(client) -> None:  # type: ignore[no-untyped-def]
    """مقدار پارامتر در برچسب یعنی یک سری تازه برای هر پروژه — انفجار کاردینالیتی."""
    project_id = uuid.uuid4()
    await client.get(f"/api/v1/projects/{project_id}")
    await client.get(f"/no-such-path/{uuid.uuid4()}")
    body = (await client.get("/metrics")).text

    assert 'route="/api/v1/projects/{project_id}"' in body
    assert str(project_id) not in body
    assert 'route="__unmatched__"' in body


async def test_metrics_token_hides_the_endpoint(settings, db_session) -> None:  # type: ignore[no-untyped-def]
    import httpx

    from silp.core.config import get_settings
    from silp.db.session import get_session
    from silp.main import create_app

    async def override_session():  # type: ignore[no-untyped-def]
        yield db_session

    guarded = settings.model_copy(update={"metrics_token": "scrape-secret"})
    app = create_app(guarded)
    app.dependency_overrides[get_settings] = lambda: guarded
    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        assert (await c.get("/metrics")).status_code == 404
        wrong = await c.get("/metrics", headers={"Authorization": "Bearer nope"})
        assert wrong.status_code == 404
        ok = await c.get("/metrics", headers={"Authorization": "Bearer scrape-secret"})
        assert ok.status_code == 200


async def test_metrics_are_not_part_of_the_public_contract(app) -> None:  # type: ignore[no-untyped-def]
    assert "/metrics" not in app.openapi()["paths"]
