"""0001 — پی‌ریزی: افزونه‌ها، uuidv7()، fa_normalize()، set_updated_at()

مرجع: PRD §4.0 — قراردادهای عمومی.
وظیفهٔ نقشهٔ راه: M0-04.

سه تابع کمکی که همهٔ مهاجرت‌های بعدی به آن‌ها تکیه می‌کنند:

* ``uuidv7()``        کلید اصلی مرتب بر حسب زمان (PG 16 نسخهٔ بومی ندارد).
* ``fa_normalize()``  یکدست‌سازی متن فارسی برای جستجو.
* ``set_updated_at()`` تریگر به‌روزرسانی ستون updated_at.

دو اصلاح نسبت به قطعه‌کد §4.0 — جزئیات و دلیل در docs/adr/0003:
۱. نگاشت ``translate`` در سند یک کاراکتر جا افتاده بود و ``ؤ``، ``ى`` و
   ``ۀ`` را به حرف اشتباه یا هیچ نگاشت می‌کرد.
۲. اعراب باید **حذف** شوند، نه با فاصله جایگزین؛ وگرنه «مُحَمَّد» به
   «م ح م د» تبدیل می‌شد و جستجو می‌شکست.

Revision ID: 0001
Revises:
Create Date: 2026-09-22
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ── افزونه‌ها — PRD §4.0 ───────────────────────────────────────────────
EXTENSIONS: tuple[str, ...] = (
    "pgcrypto",  # رمزنگاری کد ملی، gen_random_bytes
    "pg_trgm",  # جستجوی فارسی با trigram
    "unaccent",
    "citext",  # ایمیل بدون حساسیت به بزرگی حروف
)

# ── uuidv7() — PRD §4.0 ────────────────────────────────────────────────
# ۴۸ بیت اول زمان میلی‌ثانیه‌ای یونیکس، بقیه تصادفی. با ارتقا به PG 18
# این تابع حذف و تابع بومی جایگزین می‌شود (نیازمند ADR).
UUIDV7 = """
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid AS $$
DECLARE
  unix_ms  bigint := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;
  rand_a   bytea  := gen_random_bytes(10);
  ts_bytes bytea;
BEGIN
  ts_bytes := substring(int8send(unix_ms) FROM 3 FOR 6);   -- ۴۸ بیت زمان
  RETURN encode(
    ts_bytes
    -- نسخه ۷ در نیبل بالای بایت هفتم
    || set_byte(substring(rand_a FROM 1 FOR 2), 0,
                (get_byte(rand_a, 0) & 15) | 112)
    -- variant RFC 4122 در بایت نهم
    || set_byte(substring(rand_a FROM 3 FOR 8), 0,
                (get_byte(rand_a, 2) & 63) | 128),
    'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;
"""

# ── fa_normalize() — PRD §4.0 ──────────────────────────────────────────
# کاراکترهای نامرئی با نویسه‌گریز U& نوشته شده‌اند تا در ویرایشگر و در
# بازبینی کد قابل دیدن باشند:
#   \0640         کشیده (tatweel)           → حذف
#   \064B..\0670  اعراب و علائم عربی        → حذف
#   \200B..\200F  نیم‌فاصله و علائم جهت      → فاصله
# کشیده جدا از بازهٔ اعراب نوشته شده، چون U+0640 **پیش از** U+064B است و
# داخل آن بازه نمی‌افتد. اصلاح سوم ADR-0003.
#   \FEFF         ZWNBSP                    → فاصله
FA_NORMALIZE = r"""
CREATE OR REPLACE FUNCTION fa_normalize(input TEXT) RETURNS TEXT AS $$
  SELECT lower(btrim(
    regexp_replace(
      regexp_replace(
        regexp_replace(
          translate(
            COALESCE(input, ''),
            -- عربی → فارسی، نویسه‌به‌نویسه هم‌طول
            'يكةأإآؤئىۀ',
            'یکهاااوییه'
          ),
          -- اعراب و کشیده حذف می‌شوند، نه جایگزین با فاصله
          U&'[\0640\064B-\0670]+', '', 'g'
        ),
        -- نیم‌فاصله و علائم جهت به فاصله تبدیل می‌شوند
        U&'[\200B-\200F\FEFF]+', ' ', 'g'
      ),
      -- فشرده‌سازی فاصله‌های پیاپی
      '\s+', ' ', 'g'
    )
  ));
$$ LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE;
"""

# ── set_updated_at() — PRD §4.0 ────────────────────────────────────────
SET_UPDATED_AT = """
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# تابع کمکی برای مهاجرت‌های بعدی: وصل کردن تریگر به یک جدول با یک فراخوانی.
ATTACH_UPDATED_AT = """
CREATE OR REPLACE FUNCTION attach_updated_at(target_table TEXT) RETURNS void AS $$
BEGIN
  EXECUTE format(
    'DROP TRIGGER IF EXISTS trg_%1$s_updated ON %1$I;'
    ' CREATE TRIGGER trg_%1$s_updated BEFORE UPDATE ON %1$I'
    ' FOR EACH ROW EXECUTE FUNCTION set_updated_at();',
    target_table
  );
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")

    op.execute(UUIDV7)
    op.execute(FA_NORMALIZE)
    op.execute(SET_UPDATED_AT)
    op.execute(ATTACH_UPDATED_AT)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS attach_updated_at(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
    op.execute("DROP FUNCTION IF EXISTS fa_normalize(TEXT)")
    op.execute("DROP FUNCTION IF EXISTS uuidv7()")
    # افزونه‌ها حذف نمی‌شوند: ممکن است دیتابیس مشترک باشد و حذفشان
    # اشیای دیگری را با CASCADE از بین ببرد.
