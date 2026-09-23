"""اعلان — منطق خالص و آداپتورها (M6). بدون دیتابیس، بدون شبکه.

آداپتورهای HTTP با `httpx.MockTransport` آزموده می‌شوند: تشخیص «دائمی یا
گذرا» همان چیزی است که تعیین می‌کند پیام دوباره فرستاده شود یا `DEAD`.
"""

from __future__ import annotations

import importlib.util
import json
import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from silp.domain import calendar
from silp.domain.gamification.formulas import LOCAL_TZ
from silp.domain.notifications import catalog, schedule, templating
from silp.integrations.messaging import OutgoingMessage
from silp.integrations.messaging.bots import (
    EitaayarSender,
    TelegramBotSender,
    parse_telegram_start,
)
from silp.integrations.sms.kavenegar import KavenegarSMSSender
from silp.services.template_service import SAMPLE_VALUES

MIGRATION = (
    Path(__file__).resolve().parents[2] / "src/silp/db/migrations/versions/0013_messaging.py"
)


def _seeded_templates() -> tuple[tuple[str, str, str | None, str, tuple[str, ...]], ...]:
    spec = importlib.util.spec_from_file_location("migration_0013", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.TEMPLATES  # type: ignore[no-any-return]


# ── فهرست انواع و دادهٔ اولیهٔ الگو ────────────────────────────────────
def test_seeded_templates_match_catalog() -> None:
    """هر نوع اعلان الگوی داخلی دارد؛ پیامک فقط برای انواعی که اجازه دارند؛
    و هیچ الگویی متغیری به کار نمی‌برد که نوعش اعلام نکرده."""
    seeded = _seeded_templates()
    by_key = {(code, channel): (subject, body) for code, channel, subject, body, _ in seeded}

    for code, kind in catalog.KINDS.items():
        assert (code, "IN_APP") in by_key, f"{code} الگوی داخلی ندارد"
        assert ((code, "SMS") in by_key) == kind.allow_sms, f"{code}: پیامک با allow_sms نمی‌خواند"

    for code, _channel, subject, body, variables in seeded:
        allowed = catalog.template_variables(code)
        templating.validate(subject, body, allowed)
        assert set(variables) <= set(allowed), code


def test_seeded_sms_fits_one_part_with_realistic_values() -> None:
    """§14.7 — «پیامک ≤ ۷۰ نویسه (یک بخش)». با نام‌های واقع‌نما سنجیده می‌شود."""
    for code, channel, subject, body, _ in _seeded_templates():
        if channel != "SMS":
            continue
        rendered = templating.render(subject, body, SAMPLE_VALUES)
        assert templating.sms_parts(rendered.body) == 1, (code, rendered.body)


def test_every_kind_has_a_known_group_and_priority() -> None:
    for kind in catalog.KINDS.values():
        assert kind.group in catalog.GROUPS
        assert kind.priority in catalog.PRIORITIES
        assert set(kind.variables).isdisjoint(catalog.COMMON_VARIABLES)


def test_in_app_is_always_kept_and_unknown_channels_are_refused() -> None:
    assert catalog.normalize_channels("COURSE", ["SMS"]) == ("IN_APP", "SMS")
    assert catalog.normalize_channels("COURSE", []) == ("IN_APP",)
    with pytest.raises(ValueError, match="ناشناخته"):
        catalog.normalize_channels("COURSE", ["PIGEON"])


def test_default_channels_leave_course_news_off_sms() -> None:
    """ADR-0013 — «هفتهٔ تازه» هر هفته به همهٔ کلاس می‌رود؛ پیامکش مزاحم است."""
    assert "SMS" not in catalog.DEFAULT_CHANNELS["COURSE"]
    assert "SMS" in catalog.DEFAULT_CHANNELS["PROJECT"]


# ── الگو ───────────────────────────────────────────────────────────────
def test_unknown_variable_is_refused_on_save() -> None:
    with pytest.raises(templating.TemplateError, match="projct"):
        templating.validate(None, "پروژهٔ «{{projct}}»", ["project"])


def test_stray_braces_are_refused_on_save() -> None:
    with pytest.raises(templating.TemplateError, match="آکولاد"):
        templating.validate(None, "سلام {{name}", ["name"])


def test_missing_value_fails_render_instead_of_leaking_braces() -> None:
    with pytest.raises(templating.TemplateError, match="project"):
        templating.render_text("«{{project}}»", {})


def test_empty_value_leaves_no_double_space() -> None:
    text = templating.render_text("پذیرفته نشد. {{reason}} لطفاً", {"reason": ""})
    assert text == "پذیرفته نشد. لطفاً"


def test_placeholders_tolerate_inner_spaces() -> None:
    assert templating.render_text("{{ name }}", {"name": "مریم"}) == "مریم"


def test_sms_parts_counts_persian_as_ucs2() -> None:
    assert templating.sms_parts("") == 0
    assert templating.sms_parts("a" * 160) == 1
    assert templating.sms_parts("a" * 161) == 2
    assert templating.sms_parts("س" * 70) == 1
    assert templating.sms_parts("س" * 71) == 2
    assert templating.sms_parts("س" * 135) == 3


def test_excerpt_cuts_on_a_word_boundary() -> None:
    text = "جلسهٔ فردا به‌جای کلاس ۲۰۴ در آزمایشگاه برگزار می‌شود"
    cut = templating.excerpt(text, 20)
    assert cut.endswith("…")
    assert len(cut) <= 20
    assert templating.excerpt("کوتاه", 20) == "کوتاه"


# ── ساعت آرام و عقب‌نشینی ───────────────────────────────────────────────
def _tehran(hour: int, minute: int = 0, day: int = 1) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=LOCAL_TZ)


@pytest.mark.parametrize(
    ("hour", "quiet"),
    [(22, False), (23, True), (0, True), (7, True), (8, False), (12, False)],
)
def test_quiet_hours_wrap_past_midnight(hour: int, quiet: bool) -> None:
    assert schedule.in_quiet_hours(_tehran(hour), start=23, end=8) is quiet


def test_quiet_hours_are_local_not_utc() -> None:
    """۲۰:۰۰ UTC یعنی ۲۳:۳۰ تهران — آرام است، هرچند ساعت UTC آرام نیست."""
    moment = datetime(2026, 10, 1, 20, 0, tzinfo=UTC)
    assert schedule.in_quiet_hours(moment, start=23, end=8)


def test_release_time_moves_to_eight_the_next_morning() -> None:
    released = schedule.release_time(_tehran(23, 30), start=23, end=8)
    assert released.astimezone(LOCAL_TZ) == _tehran(8, 0, day=2)


def test_release_time_after_midnight_is_the_same_morning() -> None:
    released = schedule.release_time(_tehran(2, 15, day=2), start=23, end=8)
    assert released.astimezone(LOCAL_TZ) == _tehran(8, 0, day=2)


def test_release_time_outside_quiet_hours_is_unchanged() -> None:
    moment = _tehran(14)
    assert schedule.release_time(moment, start=23, end=8) == moment


def test_equal_bounds_disable_quiet_hours() -> None:
    assert not schedule.in_quiet_hours(_tehran(3), start=0, end=0)


def test_retry_delay_doubles_with_jitter() -> None:
    rng = random.Random(7)
    for attempts in range(1, schedule.MAX_ATTEMPTS + 1):
        delay = schedule.retry_delay(attempts, rng=rng)
        nominal = schedule.BASE_DELAY * (2**attempts)
        assert nominal * 0.9 <= delay <= nominal * 1.1
    with pytest.raises(ValueError):
        schedule.retry_delay(0)


def test_fifth_failure_exhausts() -> None:
    assert not schedule.is_exhausted(4)
    assert schedule.is_exhausted(5)


# ── تقویم شمسی ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("gregorian", "jalali"),
    [
        (date(2026, 3, 21), (1405, 1, 1)),
        (date(2026, 9, 23), (1405, 7, 1)),
        (date(2025, 3, 20), (1403, 12, 30)),  # ۱۴۰۳ کبیسه است
        (date(2024, 2, 29), (1402, 12, 10)),
    ],
)
def test_to_jalali(gregorian: date, jalali: tuple[int, int, int]) -> None:
    assert calendar.to_jalali(gregorian) == jalali


def test_datetime_is_formatted_in_tehran_time() -> None:
    moment = datetime(2026, 9, 30, 14, 30, tzinfo=UTC)  # ۱۸:۰۰ تهران
    assert calendar.format_datetime_fa(moment) == "۸ مهر، ساعت ۱۸:۰۰"
    assert calendar.format_date_fa(date(2026, 9, 30), with_year=True) == "۸ مهر ۱۴۰۵"


# ── کاوه‌نگار ───────────────────────────────────────────────────────────
def _kavenegar(handler: Any) -> KavenegarSMSSender:
    return KavenegarSMSSender(
        api_key="k", sender="10008663", transport=httpx.MockTransport(handler)
    )


async def test_kavenegar_success_returns_message_id() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(
            200,
            json={
                "return": {"status": 200, "message": "تایید شد"},
                "entries": [{"messageid": 8792}],
            },
        )

    result = await _kavenegar(handler).send_text("09121234567", "سلام")
    assert result.delivered and result.provider_message_id == "8792"
    assert seen["path"].endswith("/k/sms/send.json")
    assert seen["form"] == {"receptor": "09121234567", "message": "سلام", "sender": "10008663"}


async def test_kavenegar_otp_uses_the_lookup_template() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/verify/lookup.json")
        form = dict(httpx.QueryParams(request.content.decode()))
        assert form == {"receptor": "09121234567", "token": "123456", "template": "silp-otp"}
        return httpx.Response(200, json={"return": {"status": 200}, "entries": [{"messageid": 1}]})

    assert (
        await _kavenegar(handler).send_otp("09121234567", "123456", template="silp-otp")
    ).delivered


@pytest.mark.parametrize(
    ("status", "permanent"), [(411, True), (424, True), (418, False), (500, False)]
)
async def test_kavenegar_classifies_failures(status: int, permanent: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"return": {"status": status, "message": "خطا"}})

    result = await _kavenegar(handler).send_text("09121234567", "سلام")
    assert not result.delivered
    assert result.permanent is permanent
    assert str(status) in (result.error or "")


async def test_kavenegar_network_error_is_transient() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    result = await _kavenegar(handler).send_text("09121234567", "سلام")
    assert not result.delivered and not result.permanent


# ── ربات‌ها ─────────────────────────────────────────────────────────────
MESSAGE = OutgoingMessage(channel="TELEGRAM", recipient="42", subject="عنوان", body="متن")


async def test_telegram_sends_json_with_subject_first() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/botT/sendMessage"
        body = json.loads(request.content)
        assert body["chat_id"] == "42"
        assert body["text"] == "عنوان\n\nمتن"
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 5}})

    sender = TelegramBotSender(
        token="T", api_base="https://proxy.example", transport=httpx.MockTransport(handler)
    )
    result = await sender.send(MESSAGE)
    assert result.delivered and result.provider_message_id == "5"


@pytest.mark.parametrize(
    ("code", "permanent"), [(403, True), (400, True), (429, False), (502, False)]
)
async def test_telegram_classifies_failures(code: int, permanent: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={"ok": False, "error_code": code, "description": "x"})

    sender = TelegramBotSender(token="T", transport=httpx.MockTransport(handler))
    result = await sender.send(MESSAGE)
    assert not result.delivered and result.permanent is permanent


async def test_eitaa_posts_a_form() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/E/sendMessage"
        form = dict(httpx.QueryParams(request.content.decode()))
        assert form == {"chat_id": "@maryam_k", "text": "کد: ۱۲"}
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 9}})

    sender = EitaayarSender(token="E", transport=httpx.MockTransport(handler))
    message = OutgoingMessage(channel="EITAA", recipient="@maryam_k", subject=None, body="کد: ۱۲")
    assert (await sender.send(message)).delivered


def test_adapters_refuse_to_start_without_a_token() -> None:
    with pytest.raises(ValueError):
        TelegramBotSender(token="")
    with pytest.raises(ValueError):
        EitaayarSender(token="")
    with pytest.raises(ValueError):
        KavenegarSMSSender(api_key="", sender="")


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        (
            {"message": {"chat": {"id": 42, "type": "private"}, "text": "/start abc_DEF-1"}},
            ("42", "abc_DEF-1"),
        ),
        (
            {"message": {"chat": {"id": 42, "type": "private"}, "text": "/start@silp_bot tok"}},
            ("42", "tok"),
        ),
        ({"message": {"chat": {"id": -9, "type": "group"}, "text": "/start tok"}}, None),
        ({"message": {"chat": {"id": 42, "type": "private"}, "text": "/start"}}, None),
        ({"message": {"chat": {"id": 42, "type": "private"}, "text": "سلام"}}, None),
        ({"edited_message": {}}, None),
    ],
)
def test_parse_telegram_start(update: dict[str, Any], expected: tuple[str, str] | None) -> None:
    assert parse_telegram_start(update) == expected


# ── بسته‌بندی کانال بدون الگوی اختصاصی ─────────────────────────────────
def test_fallback_wrapping_per_channel() -> None:
    from silp.services.outbox_service import SIGNATURE, _wrap

    inner = templating.Rendered(subject="عنوان", body="متن")
    values = {"name": "مریم", "link": "https://silp.example/x"}
    email = _wrap("EMAIL", inner, values)
    assert email.subject == "عنوان"
    assert email.body.startswith("سلام مریم،") and email.body.endswith(SIGNATURE)
    assert "https://silp.example/x" in email.body
    assert _wrap("SMS", inner, values).body == "متن"
    assert _wrap("TELEGRAM", inner, values).body == "متن\n\nhttps://silp.example/x"
    assert _wrap("EMAIL", inner, {"name": "", "link": ""}).body.startswith("سلام،")


def test_timedelta_math_of_lease_is_minutes() -> None:
    assert schedule.LEASE == timedelta(minutes=5)
