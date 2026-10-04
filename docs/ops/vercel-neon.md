# استقرار سریع و رایگان: Vercel + Neon

مسیر فاز ۱ (ADR-0001 §مسیر دوم). مسیر اصلی و مستقل از تحریم همان داکر + VPS ایران است
(`infra/docker/compose.prod.yml`, [runbook](runbook.md)).

| بخش | پروژهٔ Vercel | نشانی |
|-----|---------------|-------|
| API | `silp-api` (ریشه `apps/api`, نقطهٔ ورود `app.py`) | https://silp-api.vercel.app |
| وب | `silp-web` (ریشه `apps/web`) | https://silp-web.vercel.app |
| دیتابیس | Neon (از Marketplace، منبع `silp-db`) | — |

نکته‌ها
- `DATABASE_URL` استاندارد Neon (`postgresql://…sslmode=require`) پذیرفته و به asyncpg تبدیل می‌شود.
- `DEV_FIXED_OTP=off` یعنی خاموش (Vercel مقدار خالی نمی‌پذیرد).
- migration و بذر از ماشین توسعه روی نشانی بدون‌استخر Neon اجرا می‌شود (`alembic upgrade head`).
- حساب مالک: `OWNER_LOGIN=… OWNER_PASSWORD=… python -m silp.scripts.bootstrap_owner`.
- ورود OTP نیاز به `SMS_API_KEY` کاوه‌نگار دارد؛ تا آن موقع فقط ورود با رمز.
- محدودیت‌ها: بدون Redis (کش/محدودیت نرخ غیرفعال)، بدون S3 (`STORAGE_PROVIDER=memory`)،
  و کارگر ARQ (صف پیام‌ها) اجرا نمی‌شود.
- `vercel env pull` مقدار متغیرهای حساس را خالی برمی‌گرداند؛ با آن اشتباهاً خالی بودن را نتیجه نگیرید.
