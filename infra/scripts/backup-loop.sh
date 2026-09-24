#!/usr/bin/env bash
# SILP — زمان‌بند پشتیبان‌گیری در کانتینر backup — NFR-10، M7-17
#
# * هر ۵ دقیقه: WAL بایگانی‌شده به فضای ابری جدا (RPO ۱۵ دقیقه، NFR-09)
# * هر روز ۴ بامداد تهران: پشتیبان منطقی + پشتیبان پایه
# * روز اول هر ماه: پشتیبان منطقی «ماهانه» با نگهداری ۱۲ ماه
#
# cron در کانتینر یعنی فرایند دوم و لاگی که `docker logs` نمی‌بیند؛ یک حلقهٔ
# ساده همان کار را می‌کند و هر خطایش در لاگ کانتینر است. شکست یک نوبت
# حلقه را نمی‌کشد — هشدار از فایل معیار می‌آید، نه از مردن کانتینر.
set -uo pipefail

export TZ="${TZ:-Asia/Tehran}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
DAILY_AT="${BACKUP_DAILY_AT:-04:00}"
HERE="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$BACKUP_DIR/wal" "$BACKUP_DIR/metrics"

sync_wal() {
  [[ -n "${BACKUP_S3_BUCKET:-}" ]] || return 0
  aws s3 sync --only-show-errors ${BACKUP_S3_ENDPOINT:+--endpoint-url "$BACKUP_S3_ENDPOINT"} \
    "$BACKUP_DIR/wal/" "s3://$BACKUP_S3_BUCKET/wal/" \
    && date -u +%s >"$BACKUP_DIR/metrics/.wal_synced_at"
  # زمان آخرین همگام‌سازی موفق WAL — هشدار RPO از همین است.
  if [[ -f "$BACKUP_DIR/metrics/.wal_synced_at" ]]; then
    printf '# TYPE silp_backup_wal_synced_timestamp_seconds gauge\nsilp_backup_wal_synced_timestamp_seconds %s\n' \
      "$(cat "$BACKUP_DIR/metrics/.wal_synced_at")" >"$BACKUP_DIR/metrics/.wal.prom.tmp"
    mv -f "$BACKUP_DIR/metrics/.wal.prom.tmp" "$BACKUP_DIR/metrics/silp_backup_wal.prom"
  fi
}

last_daily=""
echo "زمان‌بند پشتیبان: روزانه $DAILY_AT ($TZ)، WAL هر ۵ دقیقه."
while true; do
  sync_wal || echo "همگام‌سازی WAL شکست خورد؛ نوبت بعد دوباره." >&2

  today="$(date +%F)"
  if [[ "$(date +%H:%M)" > "$DAILY_AT" || "$(date +%H:%M)" == "$DAILY_AT" ]] \
     && [[ "$last_daily" != "$today" ]] \
     && [[ -z "$(find "$BACKUP_DIR/logical/daily" -maxdepth 1 -name '*.dump' -newermt "$today $DAILY_AT" 2>/dev/null)" ]]; then
    "$HERE/backup.sh" daily || echo "پشتیبان منطقی روزانه شکست خورد." >&2
    "$HERE/basebackup.sh" || echo "پشتیبان پایهٔ روزانه شکست خورد." >&2
    if [[ "$(date +%d)" == 01 ]]; then
      "$HERE/backup.sh" monthly || echo "پشتیبان ماهانه شکست خورد." >&2
    fi
    last_daily="$today"
  fi

  sleep 300
done
