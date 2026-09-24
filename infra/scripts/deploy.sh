#!/usr/bin/env bash
# SILP — استقرار یک نسخه — PRD §12.6، M7-17
#
#   infra/scripts/deploy.sh <نسخه>        (از ریشهٔ مخزن، روی سرور)
#
# ترتیب همان §12.6 است، با دو افزوده: نسخهٔ قبلی ثبت می‌شود تا rollback.sh
# بداند به کجا برگردد، و راز خراش Prometheus از .env نوشته می‌شود.
#
# مهاجرت‌ها Expand/Contract‌اند (§12.6)؛ پس کد قبلی روی اسکیمای تازه کار
# می‌کند و بازگشت خودکار فقط ایمیج را عوض می‌کند، نه دیتابیس را.
set -euo pipefail

VERSION="${1:?استفاده: deploy.sh <نسخه>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f infra/docker/compose.prod.yml --env-file .env)
STATE_DIR="$ROOT/.deploy"
mkdir -p "$STATE_DIR"

[[ -f .env ]] || { echo ".env پیدا نشد." >&2; exit 2; }
if [[ "$(stat -c %a .env)" != "600" ]]; then
  echo "دسترسی .env باید 600 باشد (§12.8)." >&2
  exit 2
fi

# راز خراش /metrics — همان METRICS_TOKEN که API می‌خواند.
metrics_token="$(grep -E '^METRICS_TOKEN=' .env | cut -d= -f2- || true)"
if [[ -z "$metrics_token" ]]; then
  echo "METRICS_TOKEN در .env خالی است؛ /metrics بی‌محافظ می‌ماند." >&2
  exit 2
fi
mkdir -p infra/monitoring/secrets
umask 077
printf '%s' "$metrics_token" >infra/monitoring/secrets/metrics_token

previous="$(cat "$STATE_DIR/current" 2>/dev/null || true)"

echo "۱. پشتیبان‌گیری پیش از استقرار"
if [[ -n "$previous" ]]; then
  VERSION="$previous" "${COMPOSE[@]}" exec -T backup backup.sh "pre-deploy-$VERSION"
else
  echo "   اولین استقرار — دیتابیسی برای پشتیبان‌گیری نیست."
fi

echo "۲. کشیدن ایمیج‌های $VERSION"
VERSION="$VERSION" "${COMPOSE[@]}" pull api worker web

echo "۳. اجرای مهاجرت‌ها"
VERSION="$VERSION" "${COMPOSE[@]}" run --rm --no-deps api alembic upgrade head

echo "۴. راه‌اندازی مجدد"
VERSION="$VERSION" "${COMPOSE[@]}" up -d --no-deps --wait api worker web

echo "۵. بررسی سلامت"
if ! "$ROOT/infra/scripts/healthcheck.sh"; then
  echo "شکست — بازگشت به نسخهٔ قبل ($previous)" >&2
  if [[ -n "$previous" ]]; then
    "$ROOT/infra/scripts/rollback.sh" "$previous"
  fi
  exit 1
fi

if [[ -n "$previous" ]]; then echo "$previous" >"$STATE_DIR/previous"; fi
echo "$VERSION" >"$STATE_DIR/current"
# nginx پیکربندی و گواهی تمدیدشده را بدون قطعی دوباره می‌خواند.
"${COMPOSE[@]}" exec -T nginx nginx -s reload || true

echo "استقرار نسخهٔ $VERSION موفق بود."
