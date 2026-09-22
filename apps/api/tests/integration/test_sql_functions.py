"""تست توابع کمکی SQL مهاجرت ۰۰۱ — §4.0، ADR-0003.

این توابع منطق واقعی دارند و در پایتون اجرا نمی‌شوند، پس فقط با یک
PostgreSQL واقعی قابل بررسی‌اند. بدون دیتابیس رد می‌شوند.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


# ── fa_normalize() — ADR-0003 ──────────────────────────────────────────
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # نگاشت عربی به فارسی
        ("كتاب", "کتاب"),
        ("مدرسة", "مدرسه"),
        ("يك", "یک"),
        # سه موردی که نسخهٔ پیش‌نویس سند غلط می‌کرد
        ("مؤسسه", "موسسه"),
        ("مسئله", "مسیله"),
        ("مصطفى", "مصطفی"),
        # اعراب حذف می‌شوند، نه جایگزین با فاصله
        ("مُحَمَّد", "محمد"),
        ("بِسْمِ", "بسم"),
        # کشیده حذف می‌شود
        ("خانـــه", "خانه"),
        # نیم‌فاصله به فاصله — §10.3 قاعدهٔ ۴
        ("می‌رود", "می رود"),
        # فاصله‌های اضافه فشرده و حذف می‌شوند. «آ» هم مثل «أ» و «إ» به
        # «ا» تا می‌شود — عمدی است: کاربر هر سه را تایپ می‌کند و جستجو
        # نباید بینشان فرق بگذارد (§4.0).
        ("  بهار   آمد  ", "بهار امد"),
        # متن لاتین کوچک می‌شود
        ("SUMO", "sumo"),
        # حالت‌های مرزی
        ("", ""),
        ("بهار", "بهار"),
    ],
)
async def test_fa_normalize(db_session, raw: str, expected: str) -> None:  # type: ignore[no-untyped-def]
    result = await db_session.scalar(text("SELECT fa_normalize(:v)"), {"v": raw})
    assert result == expected


async def test_fa_normalize_is_idempotent(db_session) -> None:  # type: ignore[no-untyped-def]
    """نرمال‌سازی دوباره نباید نتیجه را عوض کند.

    ستون‌های `*_norm` تولیدشده‌اند؛ اگر این تابع پایدار نباشد، بازسازی
    ایندکس نتیجهٔ متفاوتی می‌دهد.
    """
    sample = "مُحَمَّد مؤسسهٔ  می‌رود"
    once = await db_session.scalar(text("SELECT fa_normalize(:v)"), {"v": sample})
    twice = await db_session.scalar(text("SELECT fa_normalize(:v)"), {"v": once})
    assert once == twice


async def test_fa_normalize_handles_null(db_session) -> None:  # type: ignore[no-untyped-def]
    """تابع STRICT است: ورودی NULL خروجی NULL می‌دهد، نه خطا."""
    assert await db_session.scalar(text("SELECT fa_normalize(NULL)")) is None


async def test_fa_normalize_is_immutable(db_session) -> None:  # type: ignore[no-untyped-def]
    """IMMUTABLE بودن شرط استفاده در ستون تولیدشده است."""
    volatility = await db_session.scalar(
        text("SELECT provolatile FROM pg_proc WHERE proname = 'fa_normalize'")
    )
    # ستون `provolatile` از نوع "char" است و asyncpg آن را بایت برمی‌گرداند.
    assert volatility in ("i", b"i")


# ── uuidv7() — §4.0 ────────────────────────────────────────────────────
async def test_uuidv7_has_version_and_variant_bits(db_session) -> None:  # type: ignore[no-untyped-def]
    value = await db_session.scalar(text("SELECT uuidv7()"))
    parsed = uuid.UUID(str(value))
    assert parsed.version == 7
    # variant RFC 4122
    assert (parsed.bytes[8] & 0xC0) == 0x80


async def test_uuidv7_is_time_ordered(db_session) -> None:  # type: ignore[no-untyped-def]
    """دلیل انتخاب v7 همین است: کلیدها مرتب بر حسب زمان و ایندکس‌دوست."""
    rows = list(
        await db_session.scalars(text("SELECT uuidv7() FROM generate_series(1, 200) ORDER BY 1"))
    )
    as_text = [str(r) for r in rows]
    assert as_text == sorted(as_text)


async def test_uuidv7_is_unique(db_session) -> None:  # type: ignore[no-untyped-def]
    rows = list(await db_session.scalars(text("SELECT uuidv7() FROM generate_series(1, 1000)")))
    assert len({str(r) for r in rows}) == 1000


async def test_uuidv7_timestamp_is_current(db_session) -> None:  # type: ignore[no-untyped-def]
    """۴۸ بیت اول باید زمان یونیکس میلی‌ثانیه‌ای باشد."""
    value = uuid.UUID(str(await db_session.scalar(text("SELECT uuidv7()"))))
    unix_ms = int.from_bytes(value.bytes[:6], "big")

    now_ms = await db_session.scalar(text("SELECT (extract(epoch FROM now()) * 1000)::bigint"))
    # اختلاف چند ثانیه‌ای طبیعی است؛ چند سال نه.
    assert abs(unix_ms - int(now_ms)) < 60_000


# ── set_updated_at() و attach_updated_at() — §4.0 ──────────────────────
async def test_updated_at_trigger_fires_on_users(db_session) -> None:  # type: ignore[no-untyped-def]
    """به‌روزرسانی مستقیم SQL هم باید updated_at را به now() برساند.

    مقدار قدیمی دستی عقب برده می‌شود، چون `set_updated_at()` از `now()`
    استفاده می‌کند و `now()` **زمان شروع تراکنش** است، نه زمان دستور. دو
    نوشتن پشت‌سرهم در یک تراکنش، مهرِ زمانی یکسان می‌گیرند و مقایسهٔ
    «بعدی از قبلی بزرگ‌تر است» هرگز برقرار نمی‌شود.

    این رفتار درست است، نه اشکال: همهٔ ردیف‌های یک تراکنش باید یک زمان
    تغییر داشته باشند. چیزی که باید آزمایش شود، **شلیک شدن تریگر** است.
    """
    user_id = await db_session.scalar(
        text("INSERT INTO users (mobile) VALUES ('09129998877') RETURNING id")
    )
    await db_session.execute(
        text("UPDATE users SET updated_at = now() - interval '10 days' WHERE id = :id"),
        {"id": user_id},
    )
    # همان به‌روزرسانی بالا هم تریگر را شلیک می‌کند، پس مقدار عقب‌رفته
    # باید دوباره روی now() نشسته باشد.
    after = await db_session.scalar(
        text("SELECT updated_at FROM users WHERE id = :id"), {"id": user_id}
    )
    transaction_time = await db_session.scalar(text("SELECT now()"))

    assert after == transaction_time


# ── قیدهای مهاجرت ۰۰۲ — §4.2 ──────────────────────────────────────────
async def test_invalid_mobile_format_is_rejected(db_session) -> None:  # type: ignore[no-untyped-def]
    """قید `^09\\d{9}$` باید در سطح دیتابیس هم اعمال شود، نه فقط در اپ."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db_session.execute(text("INSERT INTO users (mobile) VALUES ('+989121234567')"))
    await db_session.rollback()


async def test_user_without_any_contact_is_rejected(db_session) -> None:  # type: ignore[no-untyped-def]
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await db_session.execute(text("INSERT INTO users (locale) VALUES ('fa')"))
    await db_session.rollback()


async def test_global_role_cannot_carry_a_scope_id(db_session) -> None:  # type: ignore[no-untyped-def]
    """قلمرو GLOBAL شناسه ندارد — حالت بی‌معنا نباید وارد جدول شود."""
    from sqlalchemy.exc import IntegrityError

    user_id = await db_session.scalar(
        text("INSERT INTO users (mobile) VALUES ('09129998866') RETURNING id")
    )
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO user_roles (user_id, role_code, scope_type, scope_id)"
                " VALUES (:u, 'STUDENT', 'GLOBAL', gen_random_uuid())"
            ),
            {"u": user_id},
        )
    await db_session.rollback()


async def test_duplicate_global_grant_is_rejected(db_session) -> None:  # type: ignore[no-untyped-def]
    """ADR-0003 — یکتایی با ایندکس عبارتی روی COALESCE(scope_id, ...)."""
    from sqlalchemy.exc import IntegrityError

    user_id = await db_session.scalar(
        text("INSERT INTO users (mobile) VALUES ('09129998855') RETURNING id")
    )
    insert = text(
        "INSERT INTO user_roles (user_id, role_code, scope_type)"
        " VALUES (:u, 'STUDENT', 'GLOBAL')"
    )
    await db_session.execute(insert, {"u": user_id})

    with pytest.raises(IntegrityError):
        await db_session.execute(insert, {"u": user_id})
    await db_session.rollback()


async def test_all_eleven_roles_are_seeded(db_session) -> None:  # type: ignore[no-untyped-def]
    """§6.1 — جدول مرجع نقش‌ها بخشی از اسکیماست، نه دادهٔ نمونه."""
    count = await db_session.scalar(text("SELECT count(*) FROM roles"))
    assert count == 11

    admin_rank = await db_session.scalar(text("SELECT rank FROM roles WHERE code = 'ADMIN'"))
    assert admin_rank == 90
