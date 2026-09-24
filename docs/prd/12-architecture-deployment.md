# ۱۲ — معماری فنی و استقرار

---

## ۱۲.۱ نمای معماری

```
                        ┌──────────────┐
                        │   کاربر      │
                        └──────┬───────┘
                               │ HTTPS
                        ┌──────┴───────┐
                        │    Nginx     │  TLS، فشرده‌سازی، محدودیت نرخ،
                        │ Reverse Proxy│  فایل‌های ایستا، هدرهای امنیتی
                        └──┬────────┬──┘
                  /api/*   │        │  /*
              ┌────────────┘        └────────────┐
              ▼                                  ▼
    ┌───────────────────┐              ┌──────────────────┐
    │   FastAPI (API)   │              │  Next.js (Web)   │
    │   uvicorn workers │              │  Node.js runtime │
    │   × ۴             │              │  SSR / RSC       │
    └─────┬──────┬──────┘              └────────┬─────────┘
          │      │                              │
          │      └──────────────────────────────┘
          │              (فراخوانی سمت سرور)
          │
   ┌──────┼──────────┬─────────────┬──────────────┐
   ▼      ▼          ▼             ▼              ▼
┌──────┐ ┌────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│Postgre│ │ Redis  │ │  MinIO   │ │ ARQ      │ │ خدمات    │
│  SQL  │ │کش و صف │ │  S3 API  │ │ Workers  │ │ خارجی    │
│  16   │ │        │ │          │ │ × ۲      │ │ پیامک و…  │
└───────┘ └────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## ۱۲.۲ ساختار مخزن

```
silp/
├── apps/
│   ├── api/                        # FastAPI
│   │   ├── src/silp/
│   │   │   ├── main.py
│   │   │   ├── core/               # پیکربندی، امنیت، مجوز، خطاها
│   │   │   │   ├── config.py
│   │   │   │   ├── security.py
│   │   │   │   ├── permissions.py
│   │   │   │   ├── exceptions.py
│   │   │   │   └── events.py
│   │   │   ├── db/
│   │   │   │   ├── session.py
│   │   │   │   ├── base.py
│   │   │   │   └── migrations/     # Alembic
│   │   │   ├── models/             # موجودیت‌های SQLAlchemy
│   │   │   ├── schemas/            # مدل‌های Pydantic
│   │   │   ├── repositories/
│   │   │   ├── services/
│   │   │   ├── domain/             # منطق خالص، بدون I/O
│   │   │   │   ├── recommendation/
│   │   │   │   ├── gamification/
│   │   │   │   ├── grading/
│   │   │   │   └── health/
│   │   │   ├── routers/v1/
│   │   │   ├── workers/            # کارهای ARQ
│   │   │   └── integrations/       # آداپتورهای پیامک، S3، تلگرام
│   │   ├── tests/
│   │   │   ├── unit/
│   │   │   ├── integration/
│   │   │   └── conftest.py
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   │
│   └── web/                        # Next.js 15
│       ├── src/
│       │   ├── app/
│       │   │   ├── (marketing)/
│       │   │   ├── (auth)/
│       │   │   ├── (app)/
│       │   │   ├── (teach)/
│       │   │   └── (admin)/
│       │   ├── components/
│       │   │   ├── ui/             # اجزای پایه
│       │   │   └── domain/         # اجزای دامنه‌ای
│       │   ├── lib/
│       │   │   ├── api/            # کلاینت تولیدشده
│       │   │   ├── auth/
│       │   │   └── format/         # تاریخ شمسی، اعداد
│       │   ├── styles/
│       │   └── messages/fa.json
│       ├── tests/e2e/
│       ├── package.json
│       └── Dockerfile
│
├── packages/
│   └── shared/                     # تایپ‌های TS تولیدشده از OpenAPI
│
├── infra/
│   ├── docker/
│   │   ├── compose.dev.yml
│   │   ├── compose.prod.yml
│   │   └── compose.test.yml
│   ├── nginx/
│   │   ├── nginx.conf
│   │   └── silp.conf
│   └── scripts/
│       ├── backup.sh
│       ├── restore.sh
│       └── restore-drill.sh
│
├── docs/
│   ├── prd/                        # این اسناد
│   ├── adr/
│   └── ops/
│
├── .github/workflows/
│   ├── ci.yml
│   └── deploy.yml
│
├── Makefile
├── .env.example
├── CLAUDE.md
└── README.md
```

---

## ۱۲.۳ محیط توسعه

**هدف: از `git clone` تا اپ در حال اجرا، یک دستور و کمتر از ۵ دقیقه.**

```bash
git clone … && cd silp
make setup      # کپی .env، ساخت ایمیج، مهاجرت، داده‌های نمونه
make dev        # بالا آوردن همه چیز
```

```makefile
setup:
	cp -n .env.example .env || true
	docker compose -f infra/docker/compose.dev.yml build
	docker compose -f infra/docker/compose.dev.yml up -d postgres redis minio
	sleep 5
	$(MAKE) migrate
	$(MAKE) seed

dev:
	docker compose -f infra/docker/compose.dev.yml up

migrate:
	docker compose -f infra/docker/compose.dev.yml run --rm api alembic upgrade head

seed:
	docker compose -f infra/docker/compose.dev.yml run --rm api python -m silp.scripts.seed

test:
	docker compose -f infra/docker/compose.test.yml run --rm api pytest
	pnpm --filter web test

e2e:
	pnpm --filter web exec playwright test

types:            # تولید تایپ‌های TS از OpenAPI
	docker compose -f infra/docker/compose.dev.yml run --rm api \
	  python -m silp.scripts.export_openapi > packages/shared/openapi.json
	pnpm exec openapi-typescript packages/shared/openapi.json \
	  -o packages/shared/src/api-types.ts

lint:
	docker compose -f infra/docker/compose.dev.yml run --rm api ruff check .
	docker compose -f infra/docker/compose.dev.yml run --rm api mypy src
	pnpm lint
```

### سرویس‌های توسعه

| سرویس | پورت | یادداشت |
|-------|------|---------|
| Next.js | ۳۰۰۰ | با Turbopack |
| FastAPI | ۸۰۰۰ | با `--reload` |
| PostgreSQL | ۵۴۳۲ | داده در volume نام‌دار |
| Redis | ۶۳۷۹ | — |
| MinIO | ۹۰۰۰ / ۹۰۰۱ | کنسول روی ۹۰۰۱ |
| MailHog | ۸۰۲۵ | دریافت ایمیل‌های توسعه |

در توسعه، OTP در لاگ چاپ می‌شود و پیامک ارسال نمی‌گردد.

---

## ۱۲.۴ تصمیم استقرار — تحلیل

سند v1 پیشنهاد داده بود فاز ۱ روی Vercel + Neon و فاز ۲ مهاجرت به VPS ایران.
بررسی این گزینه:

| معیار | Vercel + Neon | Docker + VPS ایران |
|-------|---------------|---------------------|
| سرعت راه‌اندازی اولیه | ✅ چند دقیقه | ⚠️ نیم‌روز |
| دسترسی از ایران بدون VPN | ❌ مسدود | ✅ مستقیم |
| ریسک قطع سرویس بر اثر تحریم | ❌ بالا | ✅ ندارد |
| تأخیر شبکه برای کاربر ایرانی | ⚠️ ۱۵۰-۳۰۰ms | ✅ ۱۰-۳۰ms |
| هزینهٔ ماهانه | ⚠️ ارزی | ✅ ریالی |
| اجرای کار پس‌زمینه (ARQ) | ❌ نیازمند سرویس جدا | ✅ بومی |
| اجرای FastAPI | ❌ محدود در Serverless | ✅ کامل |
| هزینهٔ مهاجرت بعدی | ❌ بالا | — |

**نتیجه (D-11):** مسیر Vercel دو مشکل ساختاری دارد که آن را برای این پروژه
نامناسب می‌کند: **اول** اینکه FastAPI با کارگر پس‌زمینه و اتصال پایدار دیتابیس
با مدل Serverless جور نیست، و **دوم** اینکه توسعه‌دهنده و کاربر هر دو در ایران
هستند و کار با پنل مسدود، اصطکاک روزانه می‌سازد.

**مسیر انتخابی:** Docker Compose از روز اول. محلی و تولید یکسان. کد ۱۲-Factor
می‌ماند، پس اگر روزی شرایط تغییر کرد، مهاجرت ممکن است.

---

## ۱۲.۵ استقرار تولید

### مشخصات سرور

| فاز | CPU | RAM | دیسک | تخمین هزینهٔ ماهانه |
|-----|-----|-----|------|---------------------|
| ۱ (۵۰۰ کاربر) | ۴ هسته | ۸GB | ۱۰۰GB SSD | ۲ تا ۴ میلیون ریال |
| ۲ (۵۰۰۰ کاربر) | ۸ هسته | ۱۶GB | ۵۰۰GB SSD | ۸ تا ۱۵ میلیون ریال |

**ارائه‌دهنده:** ابر آروان، پارس‌پک، یا آسیاتک. معیار انتخاب: پشتیبانی ۲۴ ساعته،
پشتیبان‌گیری خودکار، و امکان افزایش منابع بدون مهاجرت.

### `compose.prod.yml` — ساختار

> **پیاده‌شده در M7-17** (`infra/docker/compose.prod.yml`، ADR-0018). تفاوت با
> طرح زیر: پشتیبان‌گیری ایمیج جدا از `postgres:16` دارد (`pg_dump` ایمیج API
> نسخهٔ ۱۵ است و از سرور ۱۶ پشتیبان نمی‌گیرد)؛ `init-backups` مالکیت حجم
> `/backups` را می‌دهد؛ `certbot`، `prometheus`، `alertmanager` و `node-exporter`
> افزوده شدند؛ MinIO پشت profile `minio` است؛ nginx از قالب envsubst می‌خواند
> (`infra/nginx/templates`). راه‌اندازی و عملیات: `docs/ops/runbook.md`.

```yaml
services:
  nginx:
    image: nginx:1.27-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./infra/nginx:/etc/nginx/conf.d:ro
      - certbot-certs:/etc/letsencrypt:ro
      - web-static:/var/www/static:ro
    depends_on: [api, web]
    restart: unless-stopped

  api:
    image: silp/api:${VERSION}
    command: uvicorn silp.main:app --host 0.0.0.0 --port 8000 --workers 4
    env_file: .env
    depends_on:
      postgres: { condition: service_healthy }
      redis:    { condition: service_started }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
    deploy:
      resources: { limits: { memory: 2G } }
    restart: unless-stopped

  worker:
    image: silp/api:${VERSION}
    command: arq silp.workers.settings.WorkerSettings
    env_file: .env
    depends_on: [postgres, redis]
    deploy:
      replicas: 2
      resources: { limits: { memory: 1G } }
    restart: unless-stopped

  web:
    image: silp/web:${VERSION}
    env_file: .env
    depends_on: [api]
    restart: unless-stopped

  postgres:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./infra/postgres/postgresql.conf:/etc/postgresql/postgresql.conf:ro
    command: postgres -c config_file=/etc/postgresql/postgresql.conf
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 10s
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 512mb --maxmemory-policy allkeys-lru
    volumes: [redisdata:/data]
    restart: unless-stopped

  minio:
    image: minio/minio:latest
    command: server /data --console-address ":9001"
    volumes: [miniodata:/data]
    restart: unless-stopped

  backup:
    image: silp/api:${VERSION}
    command: /app/infra/scripts/backup-loop.sh
    volumes: [backups:/backups]
    depends_on: [postgres]
    restart: unless-stopped

volumes:
  pgdata: {}
  redisdata: {}
  miniodata: {}
  backups: {}
  certbot-certs: {}
  web-static: {}
```

### تنظیمات PostgreSQL برای ۸GB RAM

```ini
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
work_mem = 16MB
max_connections = 100
wal_level = replica
archive_mode = on
archive_command = 'test ! -f /backups/wal/%f && cp %p /backups/wal/%f'
random_page_cost = 1.1              # SSD
effective_io_concurrency = 200
shared_preload_libraries = 'pg_stat_statements'
log_min_duration_statement = 1000   # لاگ کوئری‌های کند
```

---

## ۱۲.۶ CI/CD

### خط لولهٔ CI

```yaml
# .github/workflows/ci.yml — ساختار
jobs:
  lint:       ruff · mypy --strict · eslint · tsc --noEmit · gitleaks
  test-api:   pytest با Testcontainers (Postgres واقعی) + پوشش
  test-web:   vitest + بررسی بودجهٔ باندل
  e2e:        playwright روی compose.test.yml
  a11y:       axe-core روی صفحات کلیدی
  openapi:    مقایسهٔ اسکیما با main؛ تغییر شکننده ⇒ هشدار
  build:      ساخت ایمیج و انتشار در رجیستری
```

**دروازه‌های کیفیت (شکست Build):**
- پوشش تست دامنه < ۸۰٪
- خطای `mypy` یا `eslint`
- شکست تست `axe-core`
- عبور از بودجهٔ باندل
- یافتن راز با `gitleaks`
- درخواست به دامنهٔ خارجی در HTML خروجی

### استقرار

```bash
# infra/scripts/deploy.sh
set -euo pipefail

VERSION="$1"

echo "۱. پشتیبان‌گیری پیش از استقرار"
./infra/scripts/backup.sh pre-deploy-"$VERSION"

echo "۲. کشیدن ایمیج جدید"
docker compose -f infra/docker/compose.prod.yml pull

echo "۳. اجرای مهاجرت‌ها"
docker compose -f infra/docker/compose.prod.yml run --rm api alembic upgrade head

echo "۴. راه‌اندازی مجدد بدون قطعی"
docker compose -f infra/docker/compose.prod.yml up -d --no-deps --wait api worker web

echo "۵. بررسی سلامت"
./infra/scripts/healthcheck.sh || {
  echo "شکست — بازگشت به نسخهٔ قبل"
  ./infra/scripts/rollback.sh
  exit 1
}

echo "استقرار نسخهٔ $VERSION موفق بود."
```

**پیاده‌شده در M7-17:** `deploy.sh` نسخهٔ قبلی را در `.deploy/` نگه می‌دارد تا
`rollback.sh` بداند به کجا برگردد، و راز خراش `/metrics` را از `.env` برای
Prometheus می‌نویسد. `healthcheck.sh` سه چیز را می‌سنجد: آمادگی API (دیتابیس)،
صفحهٔ اصلی و API از لبه، و اجرای موفق `close_expired_attempts` در سه دقیقهٔ
اخیر. CI کار `infra` دارد: `promtool check/test rules`، `amtool check-config`،
`nginx -t` روی قالب رندرشده و نحو اسکریپت‌ها. اسکریپت‌ها و `infra/` با
`.gitattributes` همیشه LF‌اند.

### قواعد مهاجرت دیتابیس

مهاجرت‌ها **باید با نسخهٔ قبلی کد سازگار باشند** (Expand/Contract):

```
مرحلهٔ ۱ (Expand):  افزودن ستون nullable، افزودن جدول جدید
                     ⇒ کد قدیم همچنان کار می‌کند
مرحلهٔ ۲:            استقرار کد جدید که از ستون جدید استفاده می‌کند
مرحلهٔ ۳ (Contract): حذف ستون قدیمی در استقرار بعدی
```

**ممنوع در یک استقرار:** تغییر نام ستون، حذف ستون در حال استفاده،
افزودن `NOT NULL` بدون مقدار پیش‌فرض.

---

## ۱۲.۷ پیکربندی

### متغیرهای محیطی

```bash
# ── هسته ──
ENVIRONMENT=production           # development | test | production
SECRET_KEY=                      # ۶۴ نویسهٔ تصادفی
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=30

# ── دیتابیس ──
DATABASE_URL=postgresql+asyncpg://silp:***@postgres:5432/silp
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# ── Redis ──
REDIS_URL=redis://redis:6379/0

# ── ذخیره‌سازی ──
S3_ENDPOINT=https://s3.ir-thr-at1.arvanstorage.ir
S3_BUCKET=silp-prod
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_PUBLIC_BASE=https://cdn.silp.ir

# ── پیامک ──
SMS_PROVIDER=kavenegar
SMS_API_KEY=
SMS_SENDER=10008663
SMS_OTP_TEMPLATE=silp-otp

# ── ایمیل ──
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
MAIL_FROM=noreply@silp.ir

# ── پیام‌رسان‌ها ──
TELEGRAM_BOT_TOKEN=
EITAA_API_TOKEN=
WHATSAPP_API_URL=

# ── رصد ──
SENTRY_DSN=
OTEL_EXPORTER_OTLP_ENDPOINT=
LOG_LEVEL=INFO

# ── محصول ──
FRONTEND_URL=https://silp.ir
DEFAULT_TERM_CODE=1404-2
QUIET_HOURS_START=23
QUIET_HOURS_END=8
```

**افزوده در M7-17:** `METRICS_TOKEN` (در تولید الزامی)، `WORKER_METRICS_PORT`،
`SILP_DOMAIN`، `SILP_S3_ORIGIN` (CSP)، و `BACKUP_S3_BUCKET` / `BACKUP_S3_*`
(باکت پشتیبان، جدا از باکت فایل‌ها). `.env.example` همه را دارد.

**اعتبارسنجی پیکربندی:** اپ در زمان راه‌اندازی همهٔ متغیرها را با Pydantic
Settings بررسی می‌کند و در صورت نقص، **بالا نمی‌آید**. خطای پیکربندی باید
فوری و صریح باشد، نه در اولین درخواست کاربر.

---

## ۱۲.۸ عملیات

### فهرست بررسی راه‌اندازی اولیه

- [ ] دامنه و DNS تنظیم شده
- [ ] گواهی TLS با Let's Encrypt و تمدید خودکار
- [ ] فایروال: فقط ۸۰، ۴۴۳، و SSH با کلید
- [ ] SSH با رمز عبور غیرفعال
- [ ] `fail2ban` فعال
- [ ] پشتیبان‌گیری خودکار فعال و **آزمایش بازیابی انجام‌شده**
- [ ] رصد و هشدار متصل
- [ ] `.env` با دسترسی `600` و مالک مناسب
- [ ] کاربر غیر root برای اجرای Docker
- [ ] به‌روزرسانی امنیتی خودکار سیستم‌عامل
- [ ] همگام‌سازی زمان (NTP) فعال — برای زمان‌سنج آزمون حیاتی است

### فهرست بررسی پیش از هر ترم

- [ ] آزمون بار با `k6` برای سناریوی آزمون هم‌زمان
- [ ] بررسی فضای دیسک (حداقل ۴۰٪ آزاد)
- [ ] آزمون بازیابی پشتیبان
- [ ] بررسی اعتبار گواهی TLS
- [ ] بررسی موجودی پنل پیامک
- [ ] پاک‌سازی داده‌های منقضی
- [ ] بررسی `pg_stat_statements` برای کوئری‌های کند جدید

### رویهٔ حادثه

```
۱. تشخیص      هشدار خودکار یا گزارش کاربر
۲. اعلام       صفحهٔ وضعیت + اعلان به کاربران فعال
۳. مهار        بازگشت به نسخهٔ قبل یا غیرفعال‌سازی ویژگی
۴. رفع         شناسایی و اصلاح ریشه
۵. بازیابی     تأیید سلامت کامل
۶. بازبینی     نوشتن گزارش در docs/ops/incidents/ ظرف ۴۸ ساعت
```

**قاعده:** گزارش حادثه **بدون سرزنش فرد** نوشته می‌شود. تمرکز بر اینکه
سیستم چگونه اجازهٔ وقوع این خطا را داد.

---

## ۱۲.۹ مسیر مقیاس‌پذیری

وقتی یک سرور کافی نبود، به ترتیب:

| گام | اقدام | نشانهٔ نیاز |
|-----|-------|-------------|
| ۱ | افزایش منابع سرور (عمودی) | CPU > ۷۰٪ پایدار |
| ۲ | جداسازی دیتابیس به سرور اختصاصی | رقابت I/O |
| ۳ | افزودن replica خواندنی برای گزارش‌ها | کوئری‌های سنگین تحلیلی |
| ۴ | چند نمونهٔ API پشت Load Balancer | تأخیر p95 بالا |
| ۵ | جداسازی کارگرها به سرور مجزا | صف پس‌زمینه عقب می‌افتد |
| ۶ | CDN داخلی برای فایل‌های ایستا و ویدئو | ترافیک ویدئو بالا |
| ۷ | پارتیشن‌بندی `point_entries` و `audit_logs` | > ۱۰ میلیون ردیف |

**هشدار طراحی:** اپ باید **بدون حالت (stateless)** بماند تا گام ۴ ممکن باشد.
هیچ نشست یا فایل موقتی در حافظهٔ نمونهٔ اپ ذخیره نمی‌شود.
