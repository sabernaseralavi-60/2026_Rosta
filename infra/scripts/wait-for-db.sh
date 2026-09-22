#!/usr/bin/env sh
# انتظار برای آماده شدن PostgreSQL — استفاده در `make setup`.
#
# بدون این، اولین `alembic upgrade` روی ماشین کند شکست می‌خورد و
# توسعه‌دهندهٔ تازه‌وارد فکر می‌کند پروژه خراب است.
set -eu

HOST="${POSTGRES_HOST:-postgres}"
PORT="${POSTGRES_PORT:-5432}"
USER="${POSTGRES_USER:-silp}"
DB="${POSTGRES_DB:-silp}"
TIMEOUT="${WAIT_TIMEOUT:-60}"

printf 'انتظار برای PostgreSQL روی %s:%s ' "$HOST" "$PORT"

elapsed=0
while [ "$elapsed" -lt "$TIMEOUT" ]; do
    if pg_isready -h "$HOST" -p "$PORT" -U "$USER" -d "$DB" >/dev/null 2>&1; then
        printf ' آماده است.\n'
        exit 0
    fi
    printf '.'
    sleep 1
    elapsed=$((elapsed + 1))
done

printf '\nPostgreSQL پس از %s ثانیه آماده نشد.\n' "$TIMEOUT" >&2
exit 1
