"""بررسی سلامت — M0-03.

سه سطح، چون سه سؤال متفاوت‌اند:

* ``/health``        زنده‌ام؟ — برای healthcheck داکر. هرگز به I/O دست نمی‌زند.
* ``/health/ready``  آماده‌ام؟ — دیتابیس و Redis بررسی می‌شوند.
* ``/health/live``   همان ``/health``، با نام متعارف Kubernetes.

تفکیک مهم است: اگر دیتابیس قطع شود، کانتینر نباید بازراه‌اندازی شود؛
باید ترافیک نگیرد ولی زنده بماند تا وقتی دیتابیس برگشت، بی‌درنگ ادامه دهد.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from silp.core import redis as redis_core
from silp.core.logging import get_logger
from silp.routers.deps import SessionDep, SettingsDep
from silp.schemas.common import HealthOut

log = get_logger("silp.health")

router = APIRouter(tags=["health"], include_in_schema=False)

VERSION = "0.1.0"


@router.get("/health", response_model=HealthOut, summary="زنده بودن سرویس")
async def health(settings: SettingsDep) -> HealthOut:
    return HealthOut(
        status="ok",
        environment=settings.environment,
        version=VERSION,
    )


@router.get("/health/live", response_model=HealthOut, summary="زنده بودن سرویس")
async def live(settings: SettingsDep) -> HealthOut:
    return await health(settings)


@router.get("/health/ready", response_model=HealthOut, summary="آمادگی پذیرش ترافیک")
async def ready(
    settings: SettingsDep,
    session: SessionDep,
    response: Response,
) -> HealthOut:
    """۲۰۰ فقط وقتی دیتابیس پاسخ می‌دهد.

    Redis بررسی می‌شود ولی آمادگی را رد نمی‌کند: طبق NFR-11 بدون Redis
    اپ کار می‌کند، فقط کندتر.
    """
    checks: dict[str, str] = {}

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
        healthy = True
    except Exception as exc:  # noqa: BLE001 — سلامت هرگز نباید بالا بیاید
        log.error("health_database_failed", error=str(exc))
        checks["database"] = "failed"
        healthy = False

    checks["redis"] = "ok" if await redis_core.ping() else "degraded"

    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthOut(
        status="ok" if healthy else "unavailable",
        environment=settings.environment,
        version=VERSION,
        checks=checks,
    )


__all__ = ["router"]
