#!/usr/bin/env bash
# SILP — بررسی سلامت پس از استقرار — PRD §12.6، M7-17
#
# سه چیز، چون سه شکست متفاوت‌اند:
#   ۱. API آماده است (دیتابیس پاسخ می‌دهد)       — /health/ready از داخل کانتینر
#   ۲. صفحهٔ اصلی از لبه می‌آید (nginx → web → API) — https://<دامنه>/
#   ۳. کارگر زنده است و کار ۶۰ثانیه‌ای را اجرا کرده — معیار close_expired_attempts
#
# `/health` به‌تنهایی کافی نیست: به دیتابیس دست نمی‌زند و از لبه عبور نمی‌کند.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f infra/docker/compose.prod.yml --env-file .env)
DOMAIN="$(grep -E '^SILP_DOMAIN=' .env | cut -d= -f2-)"
TRIES="${HEALTH_TRIES:-20}"

attempt() {
  local label="$1"; shift
  for ((i = 1; i <= TRIES; i++)); do
    if "$@" >/dev/null 2>&1; then
      echo "   ✓ $label"
      return 0
    fi
    sleep 3
  done
  echo "   ✗ $label" >&2
  return 1
}

attempt "API آماده (دیتابیس)" "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/health/ready
attempt "صفحهٔ اصلی از لبه" curl -fsS --max-time 10 "https://$DOMAIN/"
attempt "ورود از لبه (API از راه nginx)" curl -fsS --max-time 10 "https://$DOMAIN/api/v1/public/stats"

# کارگر: آخرین موفقیت close_expired_attempts کمتر از ۳ دقیقه پیش.
worker_ok() {
  local ts
  ts="$("${COMPOSE[@]}" exec -T worker python -c "
import urllib.request, re
body = urllib.request.urlopen('http://localhost:9101/metrics', timeout=5).read().decode()
m = re.search(r'silp_background_job_last_success_timestamp_seconds\{task=\"close_expired_attempts\"\} (\S+)', body)
print(m.group(1) if m else 0)")"
  python3 -c "import sys, time; sys.exit(0 if time.time() - float('$ts') < 180 else 1)"
}
HEALTH_TRIES=40 attempt "کارگر زنده است (close_expired_attempts)" worker_ok
