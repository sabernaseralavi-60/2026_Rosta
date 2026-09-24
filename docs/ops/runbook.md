# راهنمای عملیات تولید

> مخاطب: کسی که سرور SILP را راه می‌اندازد، به‌روز می‌کند و شب حادثه بیدار
> می‌شود. پیش‌فرض این سند یک سرور لینوکس (فاز ۱، §12.5) با داکر است.
> تصمیم‌های پشت این رویه‌ها در [ADR-0018](../adr/0018-audit-launch-data-and-production.md).

فهرست: [راه‌اندازی اولیه](#راه‌اندازی-اولیه) ·
[گواهی TLS](#گواهی-tls) · [دادهٔ راه‌اندازی](#دادهٔ-راه‌اندازی) ·
[استقرار و بازگشت](#استقرار-و-بازگشت) · [پشتیبان‌گیری](#پشتیبان‌گیری) ·
[بازیابی](#بازیابی) · [آزمون بازیابی ماهانه](#آزمون-بازیابی-ماهانه) ·
[رصد و هشدار](#رصد-و-هشدار) · [حادثه](#حادثه)

---

## راه‌اندازی اولیه

همان فهرست §12.8، با فرمان‌هایش.

1. **سیستم‌عامل:** کاربر غیر root عضو گروه `docker`؛ SSH فقط با کلید
   (`PasswordAuthentication no`)؛ `ufw allow 22,80,443/tcp`؛ `fail2ban`؛
   `unattended-upgrades`؛ `timedatectl set-ntp true` — زمان‌سنج آزمون به
   ساعت درست سرور وابسته است.
2. **آینهٔ رجیستری:** Docker Hub از ایران در دسترس نیست. در
   `/etc/docker/daemon.json` آینهٔ ارائه‌دهنده (مثلاً آروان) را بگذارید:
   ```json
   { "registry-mirrors": ["https://docker.arvancloud.ir"] }
   ```
3. **مخزن و `.env`:**
   ```bash
   git clone <repo> /srv/silp && cd /srv/silp
   cp .env.example .env && chmod 600 .env
   ```
   در `.env` دست‌کم این‌ها را پر کنید (بقیه در §12.7):

   | متغیر | مقدار |
   |-------|-------|
   | `ENVIRONMENT` | `production` |
   | `SECRET_KEY`، `JWT_SECRET_KEY` | ۶۴ نویسهٔ تصادفی: `openssl rand -hex 32` |
   | `POSTGRES_PASSWORD` | تصادفی؛ و همان در `DATABASE_URL` |
   | `SILP_DOMAIN` | مثلاً `silp.ir` |
   | `SILP_S3_ORIGIN` | مبدأ فضای ذخیره‌سازی، مثلاً `https://s3.ir-thr-at1.arvanstorage.ir` — در CSP |
   | `METRICS_TOKEN` | تصادفی؛ `deploy.sh` آن را برای Prometheus هم می‌نویسد |
   | `BACKUP_S3_BUCKET` و `BACKUP_S3_*` | باکت **جدا** از باکت فایل‌ها، ترجیحاً در منطقه یا ارائه‌دهندهٔ دیگر |
   | `SMS_PROVIDER=kavenegar`، `SMS_API_KEY` | پنل پیامک با موجودی ۵۰۰ OTP (§14.10) |
   | `DEV_FIXED_OTP` | **خالی** — در تولید نادیده گرفته می‌شود، ولی نباشد بهتر است |

4. **رازهای هشدار:** در `infra/monitoring/secrets/` (خارج از git) فایل
   `smtp_password` را بگذارید و نشانی‌های `infra/monitoring/alertmanager.yml`
   را عوض کنید. `metrics_token` را `deploy.sh` می‌نویسد.
5. **نگهداری پشتیبان در فضای ابری:** `aws s3 sync` چیزی حذف نمی‌کند؛ روی
   باکت پشتیبان قاعدهٔ lifecycle بگذارید: `logical/daily/` و
   `logical/pre-deploy/` ۳۰ روز، `logical/monthly/` ۳۶۵ روز، `base/` و
   `wal/` ۸ روز (NFR-10).

## گواهی TLS

پیکربندی کامل nginx بدون گواهی بالا نمی‌آید، پس اولین گواهی جداگانه گرفته
می‌شود — nginx موقت فقط برای چالش ACME:

```bash
docker volume create silp_certbot-www && docker volume create silp_certbot-certs
docker run -d --name acme -p 80:80 -v silp_certbot-www:/usr/share/nginx/html nginx:1.27-alpine
docker run --rm -v silp_certbot-www:/var/www/certbot -v silp_certbot-certs:/etc/letsencrypt \
  certbot/certbot:v2.11.0 certonly --webroot -w /var/www/certbot \
  -d "$SILP_DOMAIN" --email ops@silp.ir --agree-tos --no-eff-email
docker rm -f acme
```

پس از آن سرویس `certbot` در `compose.prod.yml` روزی دو بار تمدید را امتحان
می‌کند؛ `deploy.sh` در پایان `nginx -s reload` می‌زند. اگر ماه‌ها استقرار
نشد، این را در cron میزبان بگذارید:
`0 5 * * 1 cd /srv/silp && docker compose -f infra/docker/compose.prod.yml exec -T nginx nginx -s reload`

## دادهٔ راه‌اندازی

یک بار، پس از اولین `deploy.sh`:

```bash
C="docker compose -f infra/docker/compose.prod.yml --env-file .env"
LEAD=0913xxxxxxx; ADMIN=0913xxxxxxx
$C run --rm api python -m silp.scripts.seed_launch --lead-mobile $LEAD --admin-mobile $ADMIN
$C run --rm api python -m silp.scripts.sync_courses                 # ۵ درس از Courses/ — به مدیر نیاز دارد
$C run --rm api python -m silp.scripts.seed_launch --lead-mobile $LEAD   # ارائهٔ دروس تازه‌همگام‌شده
$C run --rm api python -m silp.scripts.check_coverage               # پوشش پنج پرسونا (§14.5)
```

ترتیب مهم است: `sync_courses` بدون حساب مدیر اجرا نمی‌شود و مدیر را
`seed_launch` می‌سازد؛ ارائهٔ هر درس هم فقط برای درس همگام‌شده ساخته می‌شود.

`seed_launch` بی‌اثر در تکرار است و هیچ حساب نمونه یا کد ثابت ورود نمی‌سازد
(`seed` توسعه در تولید اجرا نمی‌شود). هفته‌ها منتشر **نمی‌شوند** مگر با
`--publish-weeks N`؛ انتشار تصمیم استاد است.

این فقط **راه‌اندازی نخست** است. نیم‌سال‌های بعد، درس بی‌پوشه و ارائهٔ هر ترم با
استادش را مدیر آموزشی در پنل (`/admin/courses`) تعریف می‌کند و به سرور نیازی
نیست ([ADR-0020](../adr/0020-course-term-offering-admin.md)). درس تازه با کتاب و
جزوه همچنان با پوشهٔ `Courses/` و `sync_courses` می‌آید.

## استقرار و بازگشت

```bash
infra/scripts/deploy.sh <نسخه>      # پشتیبان پیش از استقرار ← pull ← مهاجرت ← up --wait ← سلامت
infra/scripts/rollback.sh [نسخه]    # پیش‌فرض: نسخهٔ قبلی از .deploy/previous
```

`healthcheck.sh` سه چیز را می‌سنجد: API آماده (دیتابیس)، صفحهٔ اصلی و
`/api/v1/public/stats` از لبه، و اجرای موفق `close_expired_attempts` در سه
دقیقهٔ اخیر. شکست ⇒ `deploy.sh` خودکار به نسخهٔ قبل برمی‌گردد.

**بازگشت فقط ایمیج را عوض می‌کند، نه دیتابیس.** مهاجرت‌ها Expand/Contract‌اند
(§12.6) و کد قبلی روی اسکیمای تازه کار می‌کند. اگر مهاجرتی این قاعده را شکسته
باشد، `alembic downgrade` روی تولید تصمیم آدم است — پیش از آن، پشتیبان
`pre-deploy-<نسخه>` را که `deploy.sh` گرفته پیدا کنید.

## پشتیبان‌گیری

کانتینر `backup` (ایمیج `postgres:16` — نه ایمیج API که `pg_dump` ۱۵ دارد):

| نوع | زمان | نگهداری محلی | خروجی |
|-----|------|---------------|-------|
| WAL | پیوسته؛ `archive_timeout = 900` | ۸ روز | `/backups/wal/`، هر ۵ دقیقه به باکت |
| منطقی روزانه | ۴ بامداد تهران | ۳۰ روز | `logical/daily/*.dump` + sha256 + شمار ردیف |
| پایه (فیزیکی) | ۴ بامداد تهران | ۷ روز، دست‌کم ۲ عدد | `base/<زمان>/base.tar.gz` |
| ماهانه | روز اول ماه | ۱۲ ماه | `logical/monthly/` |
| پیش از استقرار | هر `deploy.sh` | ۳۰ روز | `logical/pre-deploy/` |

پشتیبان دستی: `$C exec backup backup.sh daily`. هر اجرا فایل معیار
`/backups/metrics/*.prom` را می‌نویسد؛ شکست یا کهنگی بیش از ۲۶ ساعت هشدار
بحرانی است.

**فایل‌ها (S3):** نسخه‌بندی (versioning) باکت فایل‌ها را روشن کنید؛ حذف
تصادفی یک فایل با نسخهٔ قبلی برمی‌گردد. همگام‌سازی روزانه به باکت جدا (NFR-10)
کار ارائه‌دهندهٔ ذخیره‌سازی است (replication آروان)، نه این کانتینر.

## بازیابی

### یک پشتیبان منطقی، در دیتابیس جدا (همیشه اول این)

```bash
$C exec backup restore.sh /backups/logical/daily/silp-<زمان>.dump silp_restore
```

`restore.sh` sha256، بازیابی، شمار ردیف هر جدول و نسخهٔ مهاجرت را می‌سنجد و
**هرگز روی دیتابیس موجود نمی‌نویسد**. برای برداشتن یک ردیف پاک‌شده از همین
دیتابیس جدا کوئری بزنید.

### جایگزینی دیتابیس تولید

فقط وقتی دیتابیس تولید از دست رفته یا خراب است — تصمیم دو نفر:

```bash
$C stop api worker web                      # نوشتن متوقف
$C exec backup restore.sh <dump> silp_new   # بازیابی و سنجش در دیتابیس تازه
$C exec postgres psql -U silp -d postgres \
  -c "ALTER DATABASE silp RENAME TO silp_broken_$(date +%Y%m%d)" \
  -c "ALTER DATABASE silp_new RENAME TO silp"
$C up -d api worker web && infra/scripts/healthcheck.sh
```

`silp_broken_*` را تا پایان بررسی حادثه نگه دارید.

### بازیابی نقطه‌ای (دادهٔ پس از ۴ بامداد)

وقتی خطا (مثلاً حذف اشتباه) ساعت ۱۴:۰۵ رخ داده و دادهٔ ۴ بامداد تا ۱۴:۰۴ لازم است:

1. `postgres` را متوقف کنید؛ پوشهٔ دادهٔ فعلی را **کنار بگذارید**، پاک نکنید.
2. آخرین پشتیبان پایهٔ پیش از لحظهٔ خطا را در پوشهٔ دادهٔ خالی باز کنید:
   `tar -xzf /backups/base/<زمان>/base.tar.gz -C <پوشهٔ داده>`
3. در `postgresql.conf` بیفزایید:
   ```ini
   restore_command = 'cp /backups/wal/%f %p'
   recovery_target_time = '2026-10-12 14:04:00+03:30'
   recovery_target_action = 'promote'
   ```
   و فایل خالی `recovery.signal` را در پوشهٔ داده بسازید.
4. `postgres` را بالا بیاورید؛ در لاگ دنبال `recovery stopping before …` و
   `archive recovery complete` باشید. سپس `restore_command` و
   `recovery_target_*` را از پیکربندی بردارید.

اگر WAL محلی آسیب دیده، ابتدا `aws s3 sync s3://$BACKUP_S3_BUCKET/wal/ /backups/wal/`.

## آزمون بازیابی ماهانه

NFR-10: ماهانه، و پیش از هر ترم. نتیجه در [restore-drills.md](restore-drills.md).

1. آخرین پشتیبان روزانه را **از باکت ابری** بکشید، نه از دیسک سرور:
   `aws s3 cp s3://$BACKUP_S3_BUCKET/logical/daily/<فایل>* /backups/drill/`
2. `restore.sh /backups/drill/<فایل>.dump silp_drill_<تاریخ>` — زمان را یادداشت کنید.
3. یک API جدا روی `silp_drill_*` (مثلاً `DATABASE_URL=… uvicorn --port 8001`)
   و دست‌کم: `/health/ready`، ورود یک حساب، داشبورد، فهرست پروژه.
4. هر چند ماه یک بار بازیابی نقطه‌ای را هم روی سرور آزمایشی تکرار کنید.
5. `DROP DATABASE silp_drill_*`؛ ردیف تازه در `restore-drills.md`.

## رصد و هشدار

Prometheus و Alertmanager فقط روی `127.0.0.1` سرورند:

```bash
ssh -L 9090:127.0.0.1:9090 -L 9093:127.0.0.1:9093 ops@<سرور>
# http://localhost:9090/alerts   و   http://localhost:9093
```

| هشدار | شدت | نخستین کار |
|-------|------|-----------|
| `HighErrorRate` | بحرانی | `$C logs --since 10m api \| grep '"level": "error"'` — `trace_id` پاسخ کاربر را در لاگ بجویید |
| `ApiDown` / `WorkerDown` | بحرانی | `$C ps`؛ `$C logs --tail 200 api`؛ حافظه (`docker stats`) |
| `CloseExpiredAttemptsFailed` / `…Stalled` | بحرانی | اگر آزمونی در جریان است، استاد را خبر کنید؛ لاگ کارگر؛ `$C restart worker` |
| `BackupFailed` / `BackupStale` | بحرانی | `$C logs backup`؛ فضای دیسک؛ اجرای دستی `backup.sh daily` |
| `WalArchiveStale` | بحرانی | دسترسی به باکت؛ `$C logs backup`؛ `ls /backups/wal \| tail` |
| `QuizAnswerSaveSlow` | بحرانی | `pg_stat_statements`؛ اتصال‌ها؛ در هفتهٔ امتحان به استاد خبر دهید |
| `OutboxBacklog` / `OutboxDeadLetters` | هشدار | `/admin/notifications` — کانال مقصد؛ موجودی پنل پیامک |
| `DatabaseConnectionsHigh` | هشدار | `SELECT state, count(*) FROM pg_stat_activity GROUP BY 1` |
| `DiskAlmostFull` | هشدار | `docker system df`؛ پشتیبان‌های محلی؛ `du -sh /var/lib/docker/volumes/*` |
| `SlowResponses` | هشدار | `histogram_quantile` به تفکیک `route` در Prometheus |

آزمون قواعد هشدار: `promtool test rules infra/monitoring/alerts.test.yml`.

## حادثه

رویهٔ §12.8 (تشخیص ← اعلام ← مهار ← رفع ← بازیابی ← بازبینی). گزارش بی‌سرزنش
ظرف ۴۸ ساعت در `docs/ops/incidents/<تاریخ>-<عنوان>.md`: چه شد، چه کسی چه
زمانی فهمید، سیستم چگونه اجازهٔ آن را داد، و چه چیزی عوض می‌شود.
