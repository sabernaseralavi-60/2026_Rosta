#!/usr/bin/env bash
# SILP — پشتیبان منطقی دیتابیس — NFR-10، M7-17
#
#   backup.sh [daily|monthly|pre-deploy-<نسخه>]
#
# خروجی: $BACKUP_DIR/logical/<نوع>/silp-<زمان>.dump و کنارش:
#   .sha256         — درستی فایل پیش از بازیابی سنجیده می‌شود
#   .counts.tsv     — شمار ردیف هر جدول لحظهٔ پشتیبان؛ restore.sh با آن مقایسه می‌کند
#
# پشتیبانی که `pg_restore --list` نتواند بخواندش، پشتیبان نیست؛ همین‌جا
# سنجیده می‌شود، نه روز حادثه. نتیجه (موفق یا شکست) به فایل معیار
# node-exporter نوشته می‌شود تا هشدار «شکست پشتیبان‌گیری» (NFR-15) کور نباشد.
#
# متغیرها: PGHOST PGPORT PGUSER PGPASSWORD PGDATABASE (استاندارد libpq)،
# BACKUP_DIR (پیش‌فرض /backups)، و برای نسخهٔ بیرون از سرور:
# BACKUP_S3_BUCKET، BACKUP_S3_ENDPOINT، AWS_ACCESS_KEY_ID، AWS_SECRET_ACCESS_KEY.
set -euo pipefail

KIND="${1:-daily}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
PGDATABASE="${PGDATABASE:-silp}"
export PGDATABASE

# نگهداری — NFR-10: روزانه ۳۰ روز، ماهانه ۱۲ ماه، پیش از استقرار ۳۰ روز.
RETAIN_DAILY_DAYS="${RETAIN_DAILY_DAYS:-30}"
RETAIN_MONTHLY_DAYS="${RETAIN_MONTHLY_DAYS:-365}"

case "$KIND" in
  daily)        retain="$RETAIN_DAILY_DAYS";  group="daily" ;;
  monthly)      retain="$RETAIN_MONTHLY_DAYS"; group="monthly" ;;
  pre-deploy-*) retain="$RETAIN_DAILY_DAYS";  group="pre-deploy" ;;
  *) echo "نوع پشتیبان نامعتبر: $KIND (daily | monthly | pre-deploy-<نسخه>)" >&2; exit 2 ;;
esac

METRICS_DIR="$BACKUP_DIR/metrics"
DEST_DIR="$BACKUP_DIR/logical/$group"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
SUFFIX=""
if [[ "$KIND" != daily ]]; then SUFFIX="-$KIND"; fi
NAME="silp-${STAMP}${SUFFIX}"
DUMP="$DEST_DIR/$NAME.dump"
mkdir -p "$DEST_DIR" "$METRICS_DIR"

write_metrics() {
  # نوشتن اتمی: node-exporter هرگز فایل نیمه‌نوشته نمی‌خواند.
  local status="$1" size="${2:-0}" tmp="$METRICS_DIR/.silp_backup_logical.prom.$$"
  local previous_success=0
  if [[ -f "$METRICS_DIR/silp_backup_logical.prom" ]]; then
    previous_success="$(awk '/^silp_backup_last_success_timestamp_seconds/ {print $2}' \
      "$METRICS_DIR/silp_backup_logical.prom" || echo 0)"
  fi
  local success_ts="${previous_success:-0}"
  if [[ "$status" == 1 ]]; then success_ts="$(date -u +%s)"; fi
  {
    echo "# HELP silp_backup_last_success_timestamp_seconds آخرین پشتیبان موفق"
    echo "# TYPE silp_backup_last_success_timestamp_seconds gauge"
    echo "silp_backup_last_success_timestamp_seconds{kind=\"logical\"} $success_ts"
    echo "# HELP silp_backup_last_run_ok نتیجهٔ آخرین اجرا: ۱ موفق، ۰ شکست"
    echo "# TYPE silp_backup_last_run_ok gauge"
    echo "silp_backup_last_run_ok{kind=\"logical\"} $status"
    echo "# HELP silp_backup_size_bytes اندازهٔ آخرین پشتیبان"
    echo "# TYPE silp_backup_size_bytes gauge"
    echo "silp_backup_size_bytes{kind=\"logical\"} $size"
  } >"$tmp"
  mv -f "$tmp" "$METRICS_DIR/silp_backup_logical.prom"
}

on_error() {
  local code=$?
  echo "پشتیبان‌گیری شکست خورد (کد $code)." >&2
  rm -f "$DUMP.partial"
  write_metrics 0
  exit "$code"
}
trap on_error ERR

echo "۱. شمار ردیف جدول‌ها"
psql -X -At -v ON_ERROR_STOP=1 -F $'\t' -c "
  SELECT format('%I.%I', schemaname, relname), n
  FROM (
    SELECT schemaname, relname,
           (xpath('/row/c/text()', query_to_xml(
              format('SELECT count(*) AS c FROM %I.%I', schemaname, relname),
              false, true, '')))[1]::text::bigint AS n
    FROM pg_stat_user_tables
  ) t ORDER BY 1" >"$DEST_DIR/$NAME.counts.tsv"

echo "۲. pg_dump → $DUMP"
# فشرده‌سازی سطح ۶: ۹ برای دیتابیس چندصد مگابایتی دو برابر کندتر است و
# فقط چند درصد کوچک‌تر.
pg_dump -Fc -Z 6 --file "$DUMP.partial"
mv "$DUMP.partial" "$DUMP"

echo "۳. خواندن فهرست پشتیبان (pg_restore --list)"
entries="$(pg_restore --list "$DUMP" | grep -vc '^;' || true)"
if [[ "$entries" -lt 10 ]]; then
  echo "پشتیبان فقط $entries مدخل دارد؛ ناقص است." >&2
  false
fi

(cd "$DEST_DIR" && sha256sum "$NAME.dump" >"$NAME.dump.sha256")
size="$(wc -c <"$DUMP" | tr -d ' ')"
echo "   $entries مدخل، $size بایت"

if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  echo "۴. نسخهٔ بیرون از سرور → s3://$BACKUP_S3_BUCKET/logical/$group/"
  for f in "$DUMP" "$DUMP.sha256" "$DEST_DIR/$NAME.counts.tsv"; do
    aws s3 cp --only-show-errors ${BACKUP_S3_ENDPOINT:+--endpoint-url "$BACKUP_S3_ENDPOINT"} \
      "$f" "s3://$BACKUP_S3_BUCKET/logical/$group/"
  done
else
  echo "۴. BACKUP_S3_BUCKET تنظیم نیست — فقط نسخهٔ محلی (در تولید قابل قبول نیست)."
fi

echo "۵. حذف پشتیبان‌های قدیمی‌تر از $retain روز"
find "$DEST_DIR" -maxdepth 1 -type f -name 'silp-*' -mtime "+$retain" -print -delete

write_metrics 1 "$size"
echo "پشتیبان $NAME کامل شد."
