"""0002 — هویت و دسترسی: users, roles, user_roles, refresh_tokens, otp_challenges

مرجع: PRD §4.2 و §6.1.
وظیفهٔ نقشهٔ راه: M0-05.

نقش‌های §6.1 اینجا درج می‌شوند، چون جدول مرجع است و بدون آن هیچ کاربری
نقش نمی‌گیرد — این دادهٔ نمونه نیست، بخشی از اسکیماست.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# §6.1 — (کد، عنوان فارسی، رتبه، توضیح)
ROLES: tuple[tuple[str, str, int, str], ...] = (
    ("GUEST", "مهمان", 0, "کاربر وارد نشده"),
    ("PUBLIC_LEARNER", "فراگیر عمومی", 10, "غیر دانشجو، دسترسی به دروس عمومی"),
    ("STUDENT", "دانشجو", 20, "نقش پیش‌فرض پس از ثبت‌نام"),
    ("PROJECT_MEMBER", "عضو پروژه", 25, "مشتق از عضویت در تیم"),
    ("PROJECT_LEAD", "مدیر پروژه", 30, "سازنده یا مسئول پروژه"),
    ("MENTOR", "منتور", 40, "دانشجوی ارشد یا دستیار، بازبینی تحویل‌دادنی"),
    ("TA", "دستیار آموزشی", 45, "تصحیح، مدیریت محتوا، بدون نمرهٔ نهایی"),
    ("INSTRUCTOR", "استاد", 50, "اختیار کامل روی ارائهٔ خود"),
    ("COORDINATOR", "مدیر آموزشی", 60, "مدیریت دروس و نیم‌سال‌ها"),
    ("SUPPORT", "پشتیبانی", 70, "خواندن + جعل هویت با لاگ"),
    ("ADMIN", "مدیر سامانه", 90, "دسترسی کامل به‌جز موارد ممنوع"),
)

UUID_PK = sa.text("uuidv7()")
NOW = sa.text("now()")


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("mobile", sa.Text(), nullable=True),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("username", sa.Text(), nullable=True),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("mobile_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), server_default=sa.text("'ACTIVE'"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.Text(), server_default=sa.text("'fa'"), nullable=False),
        sa.Column("timezone", sa.Text(), server_default=sa.text("'Asia/Tehran'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("mobile", name="uq_users_mobile"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUSPENDED','DEACTIVATED')", name="ck_users_status_valid"
        ),
        sa.CheckConstraint(
            "mobile IS NOT NULL OR email IS NOT NULL", name="ck_users_contact_required"
        ),
        sa.CheckConstraint(
            r"mobile IS NULL OR mobile ~ '^09\d{9}$'", name="ck_users_mobile_format"
        ),
    )
    op.create_index(
        "idx_users_status", "users", ["status"], postgresql_where=sa.text("deleted_at IS NULL")
    )
    # جستجوی کاربر با نام کاربری در مسیر عمومی /u/{username}
    op.create_index(
        "idx_users_username_active",
        "users",
        ["username"],
        postgresql_where=sa.text("username IS NOT NULL AND deleted_at IS NULL"),
    )

    # ── roles ──────────────────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title_fa", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("code", name="pk_roles"),
    )

    # ── user_roles ─────────────────────────────────────────────────────
    op.create_table(
        "user_roles",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role_code", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), server_default=sa.text("'GLOBAL'"), nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("granted_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_roles_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["role_code"], ["roles.code"], name="fk_user_roles_role_code_roles"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_user_roles_granted_by_users"
        ),
        sa.CheckConstraint(
            "scope_type IN ('GLOBAL','OFFERING','PROJECT','VENTURE')",
            name="ck_user_roles_scope_type_valid",
        ),
        # قلمرو GLOBAL شناسه ندارد و قلمروهای دیگر بدون شناسه بی‌معنا هستند.
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND scope_id IS NULL)"
            " OR (scope_type <> 'GLOBAL' AND scope_id IS NOT NULL)",
            name="ck_user_roles_scope_id_matches_type",
        ),
    )
    # PRD کلید اصلی را روی COALESCE(scope_id, ...) تعریف می‌کند. کلید اصلی
    # در PostgreSQL نمی‌تواند عبارت باشد، پس همان تضمین با ایندکس یکتای
    # عبارتی گرفته می‌شود — اثر یکسان، نحو معتبر.
    op.create_index(
        "uq_user_roles_grant",
        "user_roles",
        [
            "user_id",
            "role_code",
            "scope_type",
            sa.text("COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid)"),
        ],
        unique=True,
    )
    op.create_index("idx_user_roles_scope", "user_roles", ["scope_type", "scope_id"])
    # ایندکس ترکیبی، نه جزئی: PostgreSQL تابع ناپایدار (`now()`) را در
    # شرط ایندکس نمی‌پذیرد — «functions in index predicate must be marked
    # IMMUTABLE». ستون `expires_at` در خود ایندکس می‌آید تا کوئری
    # `authz.load_grants` همچنان فقط ایندکس را بخواند.
    op.create_index("idx_user_roles_user_active", "user_roles", ["user_id", "expires_at"])

    # ── refresh_tokens — FR-AUTH-03 ────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_tokens"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_tokens_token_hash"),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_refresh_tokens_user_id_users",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"],
            ["refresh_tokens.id"],
            name="fk_refresh_tokens_parent_id_refresh_tokens",
        ),
    )
    op.create_index(
        "idx_refresh_user_active",
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index("idx_refresh_family", "refresh_tokens", ["family_id"])
    # پاک‌سازی دوره‌ای توکن‌های منقضی
    op.create_index("idx_refresh_expires", "refresh_tokens", ["expires_at"])

    # ── otp_challenges — FR-AUTH-01 ────────────────────────────────────
    op.create_table(
        "otp_challenges",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=UUID_PK, nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_otp_challenges"),
        sa.CheckConstraint("channel IN ('SMS','EMAIL')", name="ck_otp_challenges_channel_valid"),
        sa.CheckConstraint(
            "purpose IN ('LOGIN','VERIFY_EMAIL','VERIFY_MOBILE','RESET_PASSWORD')",
            name="ck_otp_challenges_purpose_valid",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND attempts <= max_attempts",
            name="ck_otp_challenges_attempts_bounded",
        ),
        # قید یکتایی مرکب تا تأیید بتواند چالش را با (id, destination) قفل
        # کند و شناسهٔ لو رفته به‌تنهایی برای مقصد دیگری کار نکند.
        sa.UniqueConstraint("id", "destination", name="uq_otp_challenges_id_destination"),
    )
    op.create_index(
        "idx_otp_dest_active",
        "otp_challenges",
        ["destination", "purpose"],
        postgresql_where=sa.text("consumed_at IS NULL"),
    )
    # NFR-01: OTP پس از ۲۴ ساعت فیزیکی حذف می‌شود؛ کار پس‌زمینه از این
    # ایندکس استفاده می‌کند.
    op.create_index("idx_otp_created", "otp_challenges", ["created_at"])

    # ── تریگرهای updated_at ────────────────────────────────────────────
    op.execute("SELECT attach_updated_at('users')")

    # ── دادهٔ مرجع نقش‌ها ───────────────────────────────────────────────
    op.bulk_insert(
        sa.table(
            "roles",
            sa.column("code", sa.Text),
            sa.column("title_fa", sa.Text),
            sa.column("rank", sa.Integer),
            sa.column("description", sa.Text),
        ),
        [
            {"code": code, "title_fa": title, "rank": rank, "description": desc}
            for code, title, rank, desc in ROLES
        ],
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated ON users")
    op.drop_table("otp_challenges")
    op.drop_table("refresh_tokens")
    op.drop_table("user_roles")
    op.drop_table("roles")
    op.drop_table("users")
