"""آماده‌سازی تست — D-14.

تست‌های واحد به هیچ سرویسی نیاز ندارند. تست‌های یکپارچه یک PostgreSQL و
Redis واقعی می‌خواهند و با نشانهٔ `integration` علامت خورده‌اند؛ اگر
دیتابیس در دسترس نباشد، `skip` می‌شوند نه `fail` — تا توسعه‌دهنده بتواند
بدون داکر روی منطق خالص کار کند.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0000000000000000000000000000000000")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-key-1111111111111111111111111111111111")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://silp:silp@postgres-test:5432/silp_test")
os.environ.setdefault("REDIS_URL", "redis://redis-test:6379/0")
os.environ.setdefault("SMS_PROVIDER", "memory")
os.environ.setdefault("STORAGE_PROVIDER", "memory")
os.environ.setdefault("LOG_LEVEL", "WARNING")


@pytest.fixture(autouse=True, scope="session")
def strict_event_listeners():  # type: ignore[no-untyped-def]
    """شنوندهٔ رویداد در تست خطا را بالا بیاورد، نه اینکه فقط لاگ کند.

    در تولید، شکست محاسبهٔ امتیاز نباید تأیید تحویل‌دادنی را بشکند
    (`silp.services.events`)؛ ولی همین رفتار در تست باگ امتیاز را پنهان
    می‌کند — عمل اصلی سبز می‌شود و امتیازی که باید ثبت می‌شد، بی‌صدا نیست.
    """
    from silp.services import events

    events.STRICT = True
    yield
    events.STRICT = False


@pytest.fixture(scope="session")
def settings():  # type: ignore[no-untyped-def]
    from silp.core.config import get_settings

    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def sms():  # type: ignore[no-untyped-def]
    """آداپتور پیامک در حافظه — تست کد ارسالی را از اینجا می‌خواند."""
    from silp.integrations.sms import MemorySMSSender

    return MemorySMSSender()


@pytest.fixture
def storage():  # type: ignore[no-untyped-def]
    """ذخیره‌سازی حافظه‌ای مشترک با اپ — تست نقش کلاینت آپلودکننده را بازی می‌کند.

    همان نمونه‌ای است که `get_storage` در محیط تست برمی‌گرداند، پس
    آنچه تست `put_object` می‌کند، همان است که سرویس `stat` می‌کند.
    محتوایش بین تست‌ها پاک می‌شود.
    """
    from silp.integrations.storage import get_memory_storage

    backend = get_memory_storage()
    backend.objects.clear()
    yield backend
    backend.objects.clear()


PROBE_TIMEOUT_SECONDS = 10.0

# نتیجهٔ کاوش یک بار در هر اجرا گرفته می‌شود، نه در هر تست.
#
# کاوش به‌ازای هر تست دو مشکل داشت: کند بود، و مهم‌تر اینکه یک وقفهٔ
# گذرا باعث می‌شد آن تست بی‌صدا `skip` شود. اجرایی که نیمی از تست‌هایش
# رد شده باشد ولی سبز گزارش شود، از اجرای قرمز خطرناک‌تر است.
_DATABASE_REACHABLE: bool | None = None


async def _database_reachable() -> bool:
    """بررسی یک‌بارهٔ دسترسی به دیتابیس.

    مهلت لازم است: بدون آن، اجرای تست روی ماشینی که PostgreSQL ندارد
    به‌جای رد شدن، تا مهلت TCP سیستم‌عامل معلق می‌ماند.
    """
    global _DATABASE_REACHABLE  # noqa: PLW0603
    if _DATABASE_REACHABLE is not None:
        return _DATABASE_REACHABLE

    import asyncio

    from sqlalchemy import text

    from silp.db.session import get_engine

    async def probe() -> None:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    try:
        await asyncio.wait_for(probe(), timeout=PROBE_TIMEOUT_SECONDS)
    except Exception:  # noqa: BLE001 — هر شکستی (از جمله مهلت) یعنی در دسترس نیست
        _DATABASE_REACHABLE = False
    else:
        _DATABASE_REACHABLE = True
    finally:
        # اتصال کاوش به همین حلقه گره خورده؛ رهایش نکن.
        from silp.db.session import dispose_engine as _dispose

        await _dispose()
    return _DATABASE_REACHABLE


async def _flush_redis() -> None:
    """پاک کردن حالت Redis پیش از هر تست — جزئی از جداسازی، نه یک اضافه.

    بازگردانی تراکنش فقط PostgreSQL را تمیز می‌کند. شمارندهٔ محدودیت نرخ
    OTP، کش نقش و کش پیشنهاد در Redis می‌مانند و به تست بعدی نشت می‌کنند:
    چند تست که همگی از یک شمارهٔ ثابت استفاده می‌کنند، از تست چهارم به بعد
    ۴۲۹ می‌گیرند.

    فقط در محیط `test` اجرا می‌شود؛ `FLUSHDB` روی دیتابیس توسعه، کار
    کسی را خراب می‌کند.
    """
    from redis.exceptions import RedisError

    from silp.core.config import get_settings
    from silp.core.redis import get_redis

    if not get_settings().is_test:
        return
    try:
        await get_redis().flushdb()
    except RedisError:
        # Redis اختیاری است (NFR-11) — نبودش نباید تست را متوقف کند.
        pass


async def _reset_clients() -> None:
    """بستن اتصال‌های سراسری در پایان هر تست.

    هم موتور دیتابیس و هم کلاینت Redis، متغیر سراسری‌اند و اتصالشان به
    حلقهٔ رویدادی که ساخته شده گره می‌خورد. pytest-asyncio برای هر تست
    حلقهٔ تازه می‌سازد، پس نگه‌داشتنشان یعنی «Event loop is closed» در
    تست بعدی. هزینه‌اش اتصال تازه به‌ازای هر تست است.
    """
    from silp.core.redis import close_redis
    from silp.db.session import dispose_engine

    await close_redis()
    await dispose_engine()


@pytest.fixture
async def db_session() -> AsyncIterator[object]:
    """نشست یکپارچه با بازگردانی در پایان — هیچ تستی داده جا نمی‌گذارد.

    **محدودیتی که باید بدانید:** `commit` سرویس اینجا به savepoint تبدیل
    می‌شود، پس سرویسی که فراموش کرده `commit` بزند هم تست را سبز می‌کند
    و فقط در اجرای واقعی خراب می‌شود. برای پایداری نوشتن، از
    `committing_session` استفاده کنید.

    موتور در پایان هر تست `dispose` می‌شود. دلیلش pytest-asyncio است که
    برای هر تست حلقهٔ رویداد تازه می‌سازد: اتصال‌های استخر به حلقهٔ تست
    قبلی گره خورده‌اند و در تست بعدی با «Event loop is closed» می‌شکنند.
    هزینه‌اش یک اتصال تازه به‌ازای هر تست است — برای مجموعهٔ تست ناچیز.
    """
    if not await _database_reachable():
        pytest.skip("PostgreSQL در دسترس نیست — تست یکپارچه رد شد.")
    await _flush_redis()

    from sqlalchemy.ext.asyncio import AsyncSession

    from silp.db.session import get_engine

    engine = get_engine()
    async with engine.connect() as connection:
        transaction = await connection.begin()
        # نشست داخل یک تراکنش بیرونی اجرا می‌شود و commitهای سرویس به
        # savepoint تبدیل می‌شوند؛ rollback پایانی همه را برمی‌گرداند.
        # `autoflush=False` عمدی است و باید با `get_session_factory`
        # یکی بماند (D-01). با `autoflush=True` پیش‌فرض، سرویسی که
        # نوشتهٔ هنوز flush‌نشدهٔ خودش را دوباره می‌خواند در تست درست
        # کار می‌کند و روی سرور واقعی جواب کهنه می‌گیرد — دقیقاً همان
        # جنس اشکالی که این فیکسچر باید نشان بدهد، نه پنهان کند.
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await _reset_clients()


@pytest.fixture
async def committing_session() -> AsyncIterator[object]:
    """نشست بدون تراکنش بیرونی — `commit` واقعاً می‌نویسد.

    برای تستی که باید ثابت کند داده **پس از پایان درخواست** هم هست.
    تراکنش پوششی نداریم، پس خود تست مسئول پاک‌سازی است؛ به همین دلیل
    فقط برای چند تست پایداری به کار می‌رود، نه به‌عنوان پیش‌فرض.
    """
    if not await _database_reachable():
        pytest.skip("PostgreSQL در دسترس نیست — تست یکپارچه رد شد.")
    await _flush_redis()

    from silp.db.session import get_session_factory

    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
    await _reset_clients()


@pytest.fixture
async def app(settings):  # type: ignore[no-untyped-def]
    from silp.main import create_app

    return create_app(settings)


@pytest.fixture
async def committing_client(app, committing_session):  # type: ignore[no-untyped-def]
    """کلاینت HTTP روی نشست commit‌شونده — برای تست پایداری نوشتن."""
    import httpx

    from silp.db.session import get_session

    async def override_session():  # type: ignore[no-untyped-def]
        yield committing_session

    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def client(app, db_session):  # type: ignore[no-untyped-def]
    """کلاینت HTTP که نشست تراکنشی تست را به اپ تزریق می‌کند."""
    import httpx

    from silp.db.session import get_session

    async def override_session():  # type: ignore[no-untyped-def]
        yield db_session

    app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
