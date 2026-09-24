"""پیکربندی تولید — §12.7 «اپ با پیکربندی ناقص بالا نمی‌آید»، M7-17.

تا M7 هیچ آزمونی این نگهبان را نمی‌پایید؛ هر کلید تازه‌ای که تولید لازم
دارد (مثل METRICS_TOKEN) باید همین‌جا دیده شود.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from silp.core.config import Settings

PRODUCTION: dict[str, Any] = {
    "environment": "production",
    "secret_key": "p" * 64,
    "jwt_secret_key": "j" * 64,
    "database_url": "postgresql+asyncpg://silp:x@postgres:5432/silp",
    "redis_url": "redis://redis:6379/0",
    "dev_fixed_otp": "",
    "sms_provider": "kavenegar",
    "sms_api_key": "key",
    "email_provider": "disabled",
    "telegram_provider": "disabled",
    "eitaa_provider": "disabled",
    "metrics_token": "scrape-secret",
}


def build(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**PRODUCTION, **overrides})  # type: ignore[call-arg]


def test_complete_production_settings_start() -> None:
    settings = build()
    assert settings.is_production


def test_metrics_token_is_required_in_production() -> None:
    with pytest.raises(ValidationError, match="METRICS_TOKEN"):
        build(metrics_token="")


def test_development_otp_never_reaches_production() -> None:
    with pytest.raises(ValidationError, match="DEV_FIXED_OTP"):
        build(dev_fixed_otp="111111")


def test_metrics_token_is_optional_outside_production() -> None:
    assert build(environment="development", metrics_token="", dev_fixed_otp="111111")
