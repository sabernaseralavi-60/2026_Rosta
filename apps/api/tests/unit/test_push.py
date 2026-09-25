"""Push وب — ADR-0029. منطق خالص و آداپتور، بی‌دیتابیس.

رمزنگاری را با کلید واقعی می‌آزماییم: بار پیامی که آداپتور می‌فرستد باید با
کلید خصوصی گیرنده (مرورگر) باز شود و امضای VAPID همراهش باشد. اگر کتابخانه
یا قالب بار عوض شود، این تست می‌شکند، نه مرورگر کاربر در تولید.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import http_ece
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from silp.domain.notifications import catalog
from silp.domain.notifications.push import (
    MAX_ENDPOINT_LENGTH,
    allowed_hosts,
    check_endpoint,
    endpoint_of,
    subscription_recipient,
)
from silp.integrations.messaging import OutgoingMessage, enabled_channels
from silp.integrations.messaging import webpush as webpush_module
from silp.integrations.messaging.webpush import WebPushSender, push_payload
from silp.scripts.gen_vapid_keys import generate

ALLOWED = allowed_hosts(
    "fcm.googleapis.com,updates.push.services.mozilla.com,web.push.apple.com,notify.windows.com"
)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


# ── نقطهٔ پایانی (SSRF) ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QGxyz",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
    ],
)
def test_known_push_services_are_accepted(endpoint: str) -> None:
    assert check_endpoint(endpoint, ALLOWED) is None


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # بی‌TLS
        "https://localhost/hook",
        "https://127.0.0.1/hook",
        "https://10.0.0.5:8443/hook",
        "https://[::1]/hook",
        "https://169.254.169.254/latest/meta-data",
        "https://evil.example.com/fcm.googleapis.com",
        "https://fcm.googleapis.com.evil.example/fcm/send/abc",  # پسوند شبیه
        "https://notfcm.googleapis.com.attacker.io/x",
        "https://user:pass@fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com:8443/fcm/send/abc",
        "ftp://fcm.googleapis.com/x",
        "https:///nohost",
        "",
    ],
)
def test_everything_else_is_refused(endpoint: str) -> None:
    assert check_endpoint(endpoint, ALLOWED) is not None


def test_overlong_endpoint_is_refused() -> None:
    endpoint = "https://fcm.googleapis.com/" + "a" * MAX_ENDPOINT_LENGTH
    assert check_endpoint(endpoint, ALLOWED) is not None


def test_subdomain_matches_only_on_a_label_boundary() -> None:
    assert check_endpoint("https://x.notify.windows.com/a", ALLOWED) is None
    assert check_endpoint("https://evilnotify.windows.com.x.io/a", ALLOWED) is not None
    assert check_endpoint("https://evil-notify.windows.com/a", ALLOWED) is not None


def test_recipient_round_trips_endpoint() -> None:
    recipient = subscription_recipient("https://fcm.googleapis.com/x", "P", "A")
    assert endpoint_of(recipient) == "https://fcm.googleapis.com/x"
    assert json.loads(recipient)["keys"] == {"p256dh": "P", "auth": "A"}
    assert endpoint_of("not json") is None
    assert endpoint_of("[]") is None


# ── کانال در فهرست ─────────────────────────────────────────────────────
def test_push_is_an_external_channel_with_a_title() -> None:
    assert "PUSH" in catalog.EXTERNAL_CHANNELS
    assert "PUSH" not in catalog.LINKABLE_CHANNELS  # با مرورگر وصل می‌شود، نه ربات
    assert catalog.CHANNEL_TITLE_FA["PUSH"]


def test_channel_is_enabled_only_by_its_provider() -> None:
    from silp.core.config import Settings

    off = Settings(push_provider="disabled")
    on = Settings(push_provider="memory")
    assert "PUSH" not in enabled_channels(off)
    assert "PUSH" in enabled_channels(on)


# ── بار پیام ───────────────────────────────────────────────────────────
def _message(**overrides: Any) -> OutgoingMessage:
    values: dict[str, Any] = {
        "channel": "PUSH",
        "recipient": "{}",
        "subject": "نتیجهٔ آزمون",
        "body": "نمره‌ات ثبت شد.",
        "link": "https://silp.ir/courses/abc/quizzes/1?tab=result",
        "priority": "NORMAL",
    }
    values.update(overrides)
    return OutgoingMessage(**values)


def test_payload_carries_only_a_path_never_an_absolute_url() -> None:
    payload = json.loads(push_payload(_message()))
    assert payload["url"] == "/courses/abc/quizzes/1?tab=result"
    assert payload["title"] == "نتیجهٔ آزمون"
    assert payload["urgent"] is False


def test_payload_without_a_link_opens_the_notification_center() -> None:
    assert json.loads(push_payload(_message(link=None)))["url"] == "/notifications"


def test_long_body_is_clipped_to_stay_under_the_push_limit() -> None:
    raw = push_payload(_message(body="الف" * 2000, priority="URGENT"))
    payload = json.loads(raw)
    assert payload["body"].endswith("…") and len(payload["body"]) <= 180
    assert payload["urgent"] is True
    assert len(raw.encode()) < 1000  # حد مرورگر ۴۰۹۶ بایتِ رمزشده است


# ── آداپتور با رمزنگاری واقعی ──────────────────────────────────────────
class _Response:
    def __init__(self, status: int) -> None:
        self.status_code = status
        self.text = ""
        self.reason = ""
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Session:
    def __init__(self, status: int = 201) -> None:
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append({"url": url, **kwargs})
        return _Response(self.status)


def _browser() -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any], bytes]:
    """مرورگر: جفت‌کلید و راز auth، و اشتراکی که به سرور می‌دهد."""
    key = ec.generate_private_key(ec.SECP256R1())
    auth = b"0123456789abcdef"
    public = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    subscription = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/device-1",
        "keys": {"p256dh": _b64(public), "auth": _b64(auth)},
    }
    return key, subscription, auth


async def _send(
    monkeypatch: pytest.MonkeyPatch, session: _Session, message: OutgoingMessage
) -> Any:
    _, private = generate()
    real = webpush_module.webpush
    monkeypatch.setattr(
        webpush_module,
        "webpush",
        lambda **kwargs: real(**kwargs, requests_session=session),
    )
    sender = WebPushSender(private_key=private, subject="mailto:ops@silp.ir")
    return await sender.send(message)


async def test_payload_is_encrypted_for_the_browser_and_signed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    browser_key, subscription, auth = _browser()
    session = _Session(201)
    message = _message(recipient=json.dumps(subscription), body="نمره‌ات ثبت شد.", priority="URGENT")

    result = await _send(monkeypatch, session, message)

    assert result.delivered and not result.revoked
    [call] = session.calls
    assert call["url"] == subscription["endpoint"]
    headers = {k.lower(): v for k, v in call["headers"].items()}
    assert headers["content-encoding"] == "aes128gcm"
    assert headers["urgency"] == "high"
    assert headers["ttl"] == "86400"
    assert headers["authorization"].startswith("vapid t=")
    assert "k=" in headers["authorization"]

    plain = http_ece.decrypt(call["data"], private_key=browser_key, auth_secret=auth)
    body = json.loads(plain)
    assert body["title"] == "نتیجهٔ آزمون"
    assert body["body"] == "نمره‌ات ثبت شد."
    assert body["url"] == "/courses/abc/quizzes/1?tab=result"


@pytest.mark.parametrize(
    ("status", "permanent", "revoked"),
    [
        (201, False, False),
        (404, True, True),
        (410, True, True),
        (400, True, False),
        (413, True, False),
        (401, True, False),
        (403, True, False),
        (429, False, False),
        (500, False, False),
        (503, False, False),
    ],
)
async def test_push_service_statuses_map_to_retry_policy(
    monkeypatch: pytest.MonkeyPatch, status: int, permanent: bool, revoked: bool
) -> None:
    _, subscription, _ = _browser()
    result = await _send(
        monkeypatch, _Session(status), _message(recipient=json.dumps(subscription))
    )
    if status == 201:
        assert result.delivered
        return
    assert not result.delivered
    assert result.permanent is permanent
    assert result.revoked is revoked


async def test_broken_subscription_json_is_permanent_not_a_crash() -> None:
    sender = WebPushSender(private_key="x", subject="mailto:a@b.c")
    result = await sender.send(_message(recipient="{not json"))
    assert not result.delivered and result.permanent and not result.revoked


async def test_network_failure_is_returned_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    _, subscription, _ = _browser()

    class _Down(_Session):
        def post(self, url: str, **kwargs: Any) -> _Response:
            raise ConnectionError("fcm unreachable")

    result = await _send(monkeypatch, _Down(), _message(recipient=json.dumps(subscription)))
    assert not result.delivered and not result.permanent and not result.revoked
    assert "ConnectionError" in (result.error or "")


def test_generated_keys_have_the_shape_browsers_expect() -> None:
    public, private = generate()
    assert len(_unb64(public)) == 65 and _unb64(public)[0] == 4  # نقطهٔ فشرده‌نشدهٔ P-256
    assert len(_unb64(private)) == 32
    assert "=" not in public + private
