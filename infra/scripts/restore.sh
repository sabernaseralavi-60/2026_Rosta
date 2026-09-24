#!/usr/bin/env bash
# SILP — بازیابی پشتیبان منطقی و سنجش آن — NFR-10، M7-18
#
#   restore.sh <فایل .dump> <دیتابیس مقصد>
#
# دیتابیس مقصد **نباید وجود داشته باشد**: این اسکریپت هرگز روی دیتابیسی
# بازیابی نمی‌کند که شاید دادهٔ زنده داشته باشد. برای جایگزینی دیتابیس
# تولید، رویهٔ docs/ops/runbook.md را ببینید — آن تصمیم آدم است، نه اسکریپت.
#
# سنجش پس از بازیابی:
#   ۱. sha256 فایل با فایل کنارش
#   ۲. pg_restore بی‌خطا (--exit-on-error)
#   ۳. شمار ردیف هر جدول با .counts.tsv لحظهٔ پشتیبان
#   ۴. نسخهٔ مهاجرت (alembic_version)
# زمان کل چاپ می‌شود — همان عددی که در برابر RTO دو ساعته (NFR-09) ثبت می‌شود.
set -euo pipefail

DUMP="${1:?استفاده: restore.sh <فایل .dump> <دیتابیس مقصد>}"
TARGET="${2:?دیتابیس مقصد را بدهید}"
JOBS="${RESTORE_JOBS:-4}"
started="$(date +%s)"

[[ -f "$DUMP" ]] || { echo "فایل پیدا نشد: $DUMP" >&2; exit 2; }

echo "۱. درستی فایل"
if [[ -f "$DUMP.sha256" ]]; then
  (cd "$(dirname "$DUMP")" && sha256sum --check --quiet "$(basename "$DUMP").sha256")
  echo "   sha256 درست است."
else
  echo "   هشدار: $DUMP.sha256 نیست؛ درستی فایل سنجیده نشد." >&2
fi

echo "۲. دیتابیس مقصد: $TARGET"
exists="$(psql -X -At -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$TARGET'")"
if [[ "$exists" == 1 ]]; then
  echo "دیتابیس $TARGET وجود دارد؛ بازیابی روی دیتابیس موجود ممنوع است." >&2
  exit 3
fi
createdb -T template0 -E UTF8 "$TARGET"

echo "۳. pg_restore با $JOBS کار موازی"
pg_restore --no-owner --no-privileges --exit-on-error -j "$JOBS" -d "$TARGET" "$DUMP"
restored="$(date +%s)"

echo "۴. مقایسهٔ شمار ردیف‌ها"
counts="${DUMP%.dump}.counts.tsv"
status=0
if [[ -f "$counts" ]]; then
  checked=0
  while IFS=$'\t' read -r table expected; do
    [[ -z "$table" ]] && continue
    actual="$(psql -X -At -d "$TARGET" -c "SELECT count(*) FROM $table" 2>/dev/null || echo missing)"
    checked=$((checked + 1))
    if [[ "$actual" != "$expected" ]]; then
      echo "   ✗ $table: پشتیبان $expected، بازیابی‌شده $actual"
      status=1
    fi
  done <"$counts"
  [[ "$status" == 0 ]] && echo "   همهٔ $checked جدول برابرند."
else
  echo "   هشدار: $counts نیست؛ شمار ردیف‌ها سنجیده نشد." >&2
fi

echo "۵. نسخهٔ مهاجرت"
psql -X -At -d "$TARGET" -c "SELECT '   alembic: ' || version_num FROM alembic_version"

finished="$(date +%s)"
echo ""
echo "بازیابی: $((restored - started)) ثانیه · کل با سنجش: $((finished - started)) ثانیه"
if [[ "$status" != 0 ]]; then
  echo "سنجش رد شد. اگر در لحظهٔ پشتیبان نوشتن ادامه داشت، اختلاف جدول‌های پرتردد" >&2
  echo "طبیعی است؛ بقیه را بررسی کنید (docs/ops/runbook.md)." >&2
fi
exit "$status"
