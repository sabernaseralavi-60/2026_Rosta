# SILP — Makefile
# هدف: از git clone تا اپ در حال اجرا، یک دستور و کمتر از ۵ دقیقه. (PRD §12.3)

SHELL        := /bin/bash
DC_DEV       := docker compose -f infra/docker/compose.dev.yml
DC_TEST      := docker compose -f infra/docker/compose.test.yml
RUN_API      := $(DC_DEV) run --rm --no-deps api
RUN_API_DB   := $(DC_DEV) run --rm api

.DEFAULT_GOAL := help
.PHONY: help setup dev down logs migrate revision downgrade seed shell psql redis-cli \
        test test-api test-web e2e types lint fmt check clean nuke

help: ## نمایش این راهنما
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

# ── راه‌اندازی ─────────────────────────────────────────────────────────────
setup: ## کپی .env، ساخت ایمیج‌ها، مهاجرت، داده‌های نمونه
	@test -f .env || cp .env.example .env
	$(DC_DEV) build
	$(DC_DEV) up -d postgres redis minio mailhog
	$(DC_DEV) run --rm --entrypoint /app/infra/scripts/wait-for-db.sh api
	$(MAKE) migrate
	$(MAKE) seed
	# محتوا پیش از ارائه‌ها لازم است: `seed` دوباره اجرا می‌شود تا
	# ارائه‌های دروسِ تازه‌همگام‌شده هم ساخته شوند (ADR-0008).
	$(MAKE) courses-sync
	$(MAKE) seed
	@echo ""
	@echo "  آماده است. اکنون 'make dev' را اجرا کنید."
	@echo ""

dev: ## بالا آوردن کل پشته با hot-reload
	$(DC_DEV) up

down: ## توقف سرویس‌ها (داده حفظ می‌شود)
	$(DC_DEV) down

logs: ## دنبال کردن لاگ‌ها — make logs s=api
	$(DC_DEV) logs -f $(or $(s),)

# ── دیتابیس ───────────────────────────────────────────────────────────────
migrate: ## اجرای مهاجرت‌ها تا آخرین نسخه
	$(RUN_API_DB) alembic upgrade head

revision: ## ساخت مهاجرت جدید — make revision m="add projects"
	@test -n "$(m)" || (echo "استفاده: make revision m=\"شرح تغییر\"" && exit 1)
	$(RUN_API_DB) alembic revision --autogenerate -m "$(m)"

downgrade: ## بازگشت یک مهاجرت
	$(RUN_API_DB) alembic downgrade -1

seed: ## ورود داده‌های اولیه و حساب‌های نمونهٔ توسعه
	$(RUN_API_DB) python -m silp.scripts.seed

# ── کتابخانهٔ دروس (ADR-0008) ─────────────────────────────────────────────
courses-sync: ## همگام‌سازی پوشهٔ Courses/ با کتابخانه — make courses-sync a="--course 'Traffic Safety'"
	$(RUN_API_DB) python -m silp.scripts.sync_courses $(a)

courses-check: ## گزارش بدون نوشتن: چه چیزی تازه است، چه چیزی عوض شده
	$(RUN_API_DB) python -m silp.scripts.sync_courses --dry-run

psql: ## پوستهٔ تعاملی PostgreSQL
	$(DC_DEV) exec postgres psql -U silp -d silp

redis-cli: ## پوستهٔ تعاملی Redis
	$(DC_DEV) exec redis redis-cli

shell: ## پوستهٔ bash داخل کانتینر api
	$(DC_DEV) run --rm api bash

# ── تست ───────────────────────────────────────────────────────────────────
test: test-api test-web ## اجرای همهٔ تست‌ها

test-api: ## pytest روی پشتهٔ تست (Postgres واقعی)
	$(DC_TEST) up -d postgres-test redis-test
	-$(DC_TEST) run --rm api-test pytest
	$(DC_TEST) down -v

test-web: ## vitest
	pnpm --filter web test:run

e2e: ## Playwright روی compose.test.yml
	pnpm --filter web exec playwright test

# ── کیفیت ─────────────────────────────────────────────────────────────────
lint: ## ruff + mypy + eslint + tsc
	$(RUN_API) ruff check .
	$(RUN_API) ruff format --check .
	$(RUN_API) mypy src
	pnpm --filter web lint
	pnpm --filter web typecheck

fmt: ## قالب‌بندی خودکار پایتون و تایپ‌اسکریپت
	$(RUN_API) ruff check --fix .
	$(RUN_API) ruff format .
	pnpm exec prettier --write "apps/web/src/**/*.{ts,tsx,css}"

check: lint test ## دروازهٔ کیفیت کامل — همان چیزی که CI اجرا می‌کند

# ── قرارداد API ───────────────────────────────────────────────────────────
types: ## تولید تایپ‌های TS از OpenAPI
	$(RUN_API) python -m silp.scripts.export_openapi > packages/shared/openapi.json
	pnpm exec openapi-typescript packages/shared/openapi.json -o packages/shared/src/api-types.ts

# ── پاک‌سازی ──────────────────────────────────────────────────────────────
clean: ## حذف کش‌های ساخت
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache .mypy_cache apps/web/.next

nuke: ## توقف و حذف volumeها — همهٔ دادهٔ محلی پاک می‌شود
	$(DC_DEV) down -v
