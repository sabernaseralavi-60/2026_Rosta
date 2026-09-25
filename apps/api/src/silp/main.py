"""نقطهٔ ورود اپلیکیشن FastAPI — PRD §12.2.

ترتیب افزودن میان‌افزارها معکوس اجراست: آخرین میان‌افزار افزوده‌شده اولین
اجراکننده است. `TraceMiddleware` باید بیرونی‌ترین باشد تا هر لاگ — از جمله
لاگ خطا — trace_id داشته باشد.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from silp.core.config import Settings, get_settings
from silp.core.errors import register_error_handlers
from silp.core.logging import configure_logging, get_logger
from silp.core.middleware import RequestLogMiddleware, TraceMiddleware
from silp.core.redis import close_redis
from silp.db.session import dispose_engine
from silp.routers import health
from silp.routers.v1 import (
    admin,
    admin_courses,
    applications,
    auth,
    certificates,
    city,
    courses,
    files,
    gamification,
    ideas,
    me,
    notifications,
    projects,
    public,
    qa,
    quizzes,
    research,
    search,
    subscriptions,
    taxonomy,
    teach,
    teach_quiz,
    teams,
    ventures,
    workspace,
)

log = get_logger("silp.main")

API_PREFIX = "/api/v1"

DESCRIPTION = """
API پلتفرم نوآوری و یادگیری صابر.

پاسخ‌ها مستقیماً بدنهٔ داده هستند و خطاها قالب ثابت
`{"error": {"code", "message", "details", "trace_id"}}` دارند.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    log.info(
        "api_starting",
        environment=settings.environment,
        version=app.version,
    )
    yield
    await close_redis()
    await dispose_engine()
    log.info("api_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # در توسعه لاگ رنگی و خوانا، در بقیهٔ محیط‌ها JSON ساختاریافته (NFR-13).
    configure_logging(
        settings.log_level,
        renderer="console" if settings.is_development else "json",
    )

    app = FastAPI(
        title="SILP API",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
        # مستندات تعاملی در تولید بسته است — سطح حمله را بی‌دلیل باز نکنیم.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
        swagger_ui_parameters={"persistAuthorization": True},
    )
    app.state.settings = settings

    _register_middleware(app, settings)
    register_error_handlers(app)
    _register_routers(app)

    return app


def _register_middleware(app: FastAPI, settings: Settings) -> None:
    # ترتیب معکوس: Trace بیرونی‌ترین لایه می‌شود.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Trace-Id", "Idempotency-Key"],
        expose_headers=["X-Trace-Id", "Retry-After", "Location"],
        max_age=600,
    )
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(TraceMiddleware)


def _register_routers(app: FastAPI) -> None:
    # سلامت خارج از /api/v1 است تا Nginx و داکر بدون دانستن نسخه به آن برسند.
    app.include_router(health.router)

    v1 = APIRouter(prefix=API_PREFIX)
    v1.include_router(auth.router)
    v1.include_router(me.router)
    v1.include_router(taxonomy.router)
    v1.include_router(projects.router)
    v1.include_router(workspace.router)
    v1.include_router(workspace.milestone_router)
    v1.include_router(workspace.deliverable_router)
    v1.include_router(applications.router)
    v1.include_router(files.router)
    v1.include_router(projects.feedback_router)
    # ── آموزش (M3) ─────────────────────────────────────────────────────
    v1.include_router(courses.router)
    v1.include_router(courses.offerings_router)
    v1.include_router(courses.resources_router)
    v1.include_router(courses.materials_router)
    v1.include_router(teach.router)
    v1.include_router(teach_quiz.router)
    v1.include_router(quizzes.router)
    v1.include_router(quizzes.attempts_router)
    v1.include_router(subscriptions.router)
    v1.include_router(qa.router)
    v1.include_router(qa.offering_router)
    # ── امتیاز و داشبورد (M5) ──────────────────────────────────────────
    v1.include_router(gamification.me_router)
    v1.include_router(gamification.leaderboard_router)
    v1.include_router(gamification.teach_router)
    v1.include_router(gamification.admin_router)
    # ── اعلان (M6) ─────────────────────────────────────────────────────
    v1.include_router(notifications.router)
    v1.include_router(notifications.admin_router)
    v1.include_router(notifications.integrations_router)
    # ── ایده، کارآفرینی و تیم (M7) ─────────────────────────────────────
    v1.include_router(ideas.router)
    v1.include_router(ventures.router)
    v1.include_router(ventures.metrics_router)
    v1.include_router(ventures.project_metrics_router)
    v1.include_router(ventures.revenue_router)
    v1.include_router(ventures.invitations_router)
    # ── پژوهش و تیم (M7 بخش ب) ────────────────────────────────────────
    v1.include_router(research.router)
    v1.include_router(teams.router)

    v1.include_router(city.router)
    v1.include_router(city.project_router)
    # ── عمومی، گواهی، مدیریت و جستجو (M7 بخش د) ────────────────────────
    v1.include_router(public.router)
    v1.include_router(public.profiles_router)
    v1.include_router(certificates.public_router)
    v1.include_router(certificates.me_router)
    v1.include_router(certificates.admin_router)
    v1.include_router(admin.router)
    v1.include_router(admin_courses.router)
    v1.include_router(search.router)
    app.include_router(v1)


app = create_app()
