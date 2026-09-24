#!/usr/bin/env bash
# SILP — بازگشت به نسخهٔ قبل — PRD §12.6، M7-17
#
#   infra/scripts/rollback.sh [نسخه]     (پیش‌فرض: .deploy/previous)
#
# فقط ایمیج‌ها برمی‌گردند، دیتابیس نه: مهاجرت‌ها Expand/Contract‌اند و کد
# قبلی روی اسکیمای تازه کار می‌کند (§12.6). اگر مهاجرتی این قاعده را شکسته
# باشد، بازگشت دیتابیس تصمیم آدم است — docs/ops/runbook.md «بازگشت».
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE=(docker compose -f infra/docker/compose.prod.yml --env-file .env)
TARGET="${1:-$(cat .deploy/previous 2>/dev/null || true)}"
[[ -n "$TARGET" ]] || { echo "نسخهٔ قبلی ثبت نشده؛ نسخه را صریح بدهید." >&2; exit 2; }

echo "بازگشت به $TARGET"
VERSION="$TARGET" "${COMPOSE[@]}" up -d --no-deps --wait api worker web
"$ROOT/infra/scripts/healthcheck.sh"
echo "$TARGET" >.deploy/current
echo "بازگشت به $TARGET کامل شد."
