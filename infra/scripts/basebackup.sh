#!/usr/bin/env bash
# SILP — پشتیبان فیزیکی برای بازیابی نقطه‌ای — NFR-09 (RPO ۱۵ دقیقه)، M7-17
#
# pg_dump لحظهٔ اجرایش را نگه می‌دارد، نه لحظه‌های بینش را؛ با آن فقط تا ۴
# بامداد دیروز می‌شود برگشت. بازیابی نقطه‌ای یعنی «پشتیبان پایه + WAL
# بایگانی‌شده تا لحظهٔ دلخواه». این اسکریپت پشتیبان پایه را می‌سازد؛ WAL را
# خود PostgreSQL با archive_command در $BACKUP_DIR/wal می‌گذارد.
#
# `-X fetch`: WAL لازم برای سازگاری خود پشتیبان داخل آن است، پس حتی اگر
# بایگانی WAL آسیب ببیند، این پشتیبان به‌تنهایی قابل بازیابی است.
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/backups}"
# NFR-10 — WAL پیوسته ۷ روز؛ پشتیبان پایه‌ای قدیمی‌تر از WAL موجود بی‌فایده است.
RETAIN_WAL_DAYS="${RETAIN_WAL_DAYS:-7}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DEST="$BACKUP_DIR/base/$STAMP"
METRICS_DIR="$BACKUP_DIR/metrics"
mkdir -p "$BACKUP_DIR/base" "$BACKUP_DIR/wal" "$METRICS_DIR"

write_metrics() {
  local status="$1" tmp="$METRICS_DIR/.silp_backup_base.prom.$$" success_ts=0
  if [[ -f "$METRICS_DIR/silp_backup_base.prom" ]]; then
    success_ts="$(awk '/^silp_backup_last_success_timestamp_seconds/ {print $2}' \
      "$METRICS_DIR/silp_backup_base.prom" || echo 0)"
  fi
  if [[ "$status" == 1 ]]; then success_ts="$(date -u +%s)"; fi
  {
    echo "# TYPE silp_backup_last_success_timestamp_seconds gauge"
    echo "silp_backup_last_success_timestamp_seconds{kind=\"base\"} ${success_ts:-0}"
    echo "# TYPE silp_backup_last_run_ok gauge"
    echo "silp_backup_last_run_ok{kind=\"base\"} $status"
  } >"$tmp"
  mv -f "$tmp" "$METRICS_DIR/silp_backup_base.prom"
}
trap 'code=$?; echo "پشتیبان پایه شکست خورد (کد $code)." >&2; rm -rf "$DEST"; write_metrics 0; exit $code' ERR

echo "۱. pg_basebackup → $DEST"
pg_basebackup -D "$DEST" -Ft -z -X fetch --checkpoint=fast --label "silp-$STAMP" \
  --manifest-checksums=SHA256

echo "۲. سنجش manifest"
# pg_verifybackup قالب tar را نمی‌خواند (تا نسخهٔ ۱۶)؛ دست‌کم manifest و
# سالم بودن gzip هر tar سنجیده می‌شود.
test -s "$DEST/backup_manifest"
for tarball in "$DEST"/*.tar.gz; do gzip -t "$tarball"; done

if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
  echo "۳. نسخهٔ بیرون از سرور"
  aws s3 cp --only-show-errors --recursive ${BACKUP_S3_ENDPOINT:+--endpoint-url "$BACKUP_S3_ENDPOINT"} \
    "$DEST" "s3://$BACKUP_S3_BUCKET/base/$STAMP/"
fi

echo "۴. حذف پشتیبان پایه و WAL قدیمی‌تر از $RETAIN_WAL_DAYS روز"
# همیشه دست‌کم دو پشتیبان پایه می‌ماند، حتی اگر همه قدیمی باشند.
mapfile -t bases < <(find "$BACKUP_DIR/base" -mindepth 1 -maxdepth 1 -type d | sort)
if (( ${#bases[@]} > 2 )); then
  for dir in "${bases[@]:0:${#bases[@]}-2}"; do
    if [[ -n "$(find "$dir" -maxdepth 0 -mtime "+$RETAIN_WAL_DAYS")" ]]; then
      rm -rf "$dir" && echo "   حذف $dir"
    fi
  done
fi
find "$BACKUP_DIR/wal" -maxdepth 1 -type f -mtime "+$((RETAIN_WAL_DAYS + 1))" -delete

write_metrics 1
echo "پشتیبان پایه $STAMP کامل شد."
