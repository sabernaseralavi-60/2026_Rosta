"""پیکربندی اپلیکیشن — PRD §12.7.

اپ در زمان راه‌اندازی همهٔ متغیرها را اعتبارسنجی می‌کند و در صورت نقص بالا
نمی‌آید. خطای پیکربندی باید فوری و صریح باشد، نه در اولین درخواست کاربر.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]

# طول کمینهٔ کلیدها؛ کوتاه‌تر از این در تولید پذیرفته نمی‌شود.
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── هسته ───────────────────────────────────────────────────────────
    environment: Environment = "development"
    secret_key: str = Field(min_length=MIN_SECRET_LENGTH)
    jwt_secret_key: str = Field(min_length=MIN_SECRET_LENGTH)
    jwt_algorithm: str = "HS256"
    access_token_minutes: Annotated[int, Field(ge=1, le=120)] = 15
    refresh_token_days: Annotated[int, Field(ge=1, le=365)] = 30
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # ── دیتابیس ────────────────────────────────────────────────────────
    database_url: PostgresDsn
    db_pool_size: Annotated[int, Field(ge=1, le=100)] = 20
    db_max_overflow: Annotated[int, Field(ge=0, le=100)] = 10
    db_statement_timeout_ms: Annotated[int, Field(ge=1000)] = 10_000
    db_echo: bool = False

    # ── Redis ──────────────────────────────────────────────────────────
    redis_url: RedisDsn = RedisDsn("redis://redis:6379/0")

    # ── ذخیره‌سازی ─────────────────────────────────────────────────────
    storage_provider: Literal["s3", "memory"] = "s3"
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "silp-dev"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_public_base: str = ""
    # §5.9 — عمر URL امضاشده. کوتاه‌تر امن‌تر است، ولی آپلود ۵۰۰ مگابایتی
    # روی اینترنت ایران در ۹۰۰ ثانیه هم ممکن است تمام نشود.
    upload_url_ttl_seconds: Annotated[int, Field(ge=60, le=7200)] = 900
    download_url_ttl_seconds: Annotated[int, Field(ge=60, le=3600)] = 900
    # FR-EDU-03 — سقف‌ها «قابل تنظیم» هستند؛ پیش‌فرض همان سند است.
    upload_max_mb_document: Annotated[int, Field(ge=1, le=500)] = 50
    upload_max_mb_image: Annotated[int, Field(ge=1, le=500)] = 10
    upload_max_mb_video: Annotated[int, Field(ge=1, le=500)] = 500
    upload_max_mb_dataset: Annotated[int, Field(ge=1, le=500)] = 200
    upload_max_mb_archive: Annotated[int, Field(ge=1, le=500)] = 200

    # ── کتابخانهٔ درس (ADR-0008) ───────────────────────────────────────
    # پوشه‌ای که هر زیرپوشه‌اش یک درس است. نسبی یعنی نسبت به ریشهٔ مخزن.
    courses_dir: str = "Courses"

    # ── احراز هویت (FR-AUTH-01) ────────────────────────────────────────
    otp_length: Annotated[int, Field(ge=4, le=8)] = 6
    otp_ttl_seconds: Annotated[int, Field(ge=30, le=600)] = 120
    otp_resend_after_seconds: Annotated[int, Field(ge=10, le=300)] = 60
    otp_max_attempts: Annotated[int, Field(ge=1, le=10)] = 3
    otp_per_destination_per_10min: Annotated[int, Field(ge=1)] = 3
    otp_per_ip_per_hour: Annotated[int, Field(ge=1)] = 10
    dev_fixed_otp: str | None = "111111"

    # ── پیامک ──────────────────────────────────────────────────────────
    sms_provider: Literal["console", "memory", "kavenegar"] = "console"
    sms_api_key: str = ""
    sms_sender: str = ""
    sms_otp_template: str = "silp-otp"

    sms_api_base: str = "https://api.kavenegar.com/v1"

    # ── ایمیل ──────────────────────────────────────────────────────────
    # `disabled` یعنی کانال ایمیل در ترجیحات کاربر پیشنهاد نمی‌شود.
    email_provider: Literal["console", "memory", "smtp", "disabled"] = "console"
    smtp_host: str = ""
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    mail_from: str = "noreply@silp.local"

    # ── پیام‌رسان‌ها (M6-06) ───────────────────────────────────────────
    # تلگرام در ایران فیلتر است؛ `TELEGRAM_API_BASE` می‌تواند به یک
    # پروکسی خارج از کشور اشاره کند. شکست این کانال بقیه را متوقف
    # نمی‌کند (FR-MSG-02).
    telegram_provider: Literal["disabled", "console", "memory", "bot"] = "disabled"
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    # هدر `X-Telegram-Bot-Api-Secret-Token` وب‌هوک — بدون آن هر کسی
    # می‌تواند خود را «تلگرام» جا بزند و حساب دیگری را پیوند دهد.
    telegram_webhook_secret: str = ""
    eitaa_provider: Literal["disabled", "console", "memory", "eitaayar"] = "disabled"
    eitaa_api_token: str = ""
    eitaa_api_base: str = "https://eitaayar.ir/api"
    messaging_timeout_seconds: Annotated[float, Field(gt=0, le=60)] = 10.0

    # ── صف ارسال (§7.10) ───────────────────────────────────────────────
    outbox_batch_size: Annotated[int, Field(ge=1, le=500)] = 50
    outbox_concurrency: Annotated[int, Field(ge=1, le=50)] = 8

    # ── رصد ────────────────────────────────────────────────────────────
    sentry_dsn: str = ""
    otel_exporter_otlp_endpoint: str = ""

    # ── محصول ──────────────────────────────────────────────────────────
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"
    default_term_code: str = "1404-2"
    quiet_hours_start: Annotated[int, Field(ge=0, le=23)] = 23
    quiet_hours_end: Annotated[int, Field(ge=0, le=23)] = 8
    # §7.7 «آستانهٔ تنظیمات» برای گذار FIRST_REVENUE → GROWTH، به ریال.
    venture_growth_threshold_rial: Annotated[int, Field(ge=1)] = 500_000_000

    # ── مشتق‌ها ────────────────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"

    @property
    def is_test(self) -> bool:
        return self.environment == "test"

    @property
    def upload_limit_overrides(self) -> dict[str, int]:
        """سقف هر دسته به بایت — کلید با `domain.files.Category` یکی است."""
        mb = 1024 * 1024
        return {
            "DOCUMENT": self.upload_max_mb_document * mb,
            "IMAGE": self.upload_max_mb_image * mb,
            "VIDEO": self.upload_max_mb_video * mb,
            "DATASET": self.upload_max_mb_dataset * mb,
            "ARCHIVE": self.upload_max_mb_archive * mb,
        }

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """آدرس همگام برای ابزارهایی که async نمی‌فهمند (مثل بعضی مسیرهای Alembic)."""
        return str(self.database_url).replace("postgresql+asyncpg://", "postgresql://")

    # ── اعتبارسنجی ─────────────────────────────────────────────────────
    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, v: PostgresDsn) -> PostgresDsn:
        if not str(v).startswith("postgresql+asyncpg://"):
            msg = "DATABASE_URL باید با postgresql+asyncpg:// شروع شود (D-01)."
            raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def _production_hardening(self) -> Settings:
        """در تولید، مقادیر توسعه‌ای باید قطعاً غایب باشند."""
        if not self.is_production:
            return self

        problems: list[str] = []
        if self.dev_fixed_otp:
            problems.append("DEV_FIXED_OTP باید در تولید خالی باشد.")
        if self.sms_provider in ("console", "memory"):
            problems.append("SMS_PROVIDER در تولید نمی‌تواند console یا memory باشد.")
        if "dev-only" in self.secret_key or "dev-only" in self.jwt_secret_key:
            problems.append("کلیدهای نمونهٔ .env.example در تولید قابل استفاده نیستند.")
        if self.secret_key == self.jwt_secret_key:
            problems.append("SECRET_KEY و JWT_SECRET_KEY باید متفاوت باشند.")
        if self.sms_provider == "kavenegar" and not self.sms_api_key:
            problems.append("SMS_API_KEY برای کاوه‌نگار لازم است.")
        if self.email_provider in ("console", "memory"):
            problems.append("EMAIL_PROVIDER در تولید باید smtp یا disabled باشد.")
        if self.email_provider == "smtp" and not self.smtp_host:
            problems.append("SMTP_HOST برای EMAIL_PROVIDER=smtp لازم است.")
        if self.telegram_provider in ("console", "memory") or self.eitaa_provider in (
            "console",
            "memory",
        ):
            problems.append("پیام‌رسان‌ها در تولید باید bot/eitaayar یا disabled باشند.")
        if self.telegram_provider == "bot" and not (
            self.telegram_bot_token and self.telegram_bot_username and self.telegram_webhook_secret
        ):
            problems.append(
                "TELEGRAM_BOT_TOKEN، TELEGRAM_BOT_USERNAME و TELEGRAM_WEBHOOK_SECRET لازم‌اند."
            )
        if self.eitaa_provider == "eitaayar" and not self.eitaa_api_token:
            problems.append("EITAA_API_TOKEN برای ایتایار لازم است.")
        if problems:
            raise ValueError(" ".join(problems))
        return self

    @model_validator(mode="after")
    def _otp_windows_are_coherent(self) -> Settings:
        if self.otp_resend_after_seconds > self.otp_ttl_seconds:
            msg = "OTP_RESEND_AFTER_SECONDS نمی‌تواند از OTP_TTL_SECONDS بیشتر باشد."
            raise ValueError(msg)
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """تنها نقطهٔ ورود به پیکربندی. نتیجه کش می‌شود تا در هر درخواست ساخته نشود."""
    # مقادیر از محیط خوانده می‌شوند؛ آرگومان صریحی لازم نیست.
    return Settings()


def generate_secret(length: int = 64) -> str:
    """تولید کلید تصادفی — برای اسکریپت راه‌اندازی تولید."""
    return secrets.token_urlsafe(length)[:length]
