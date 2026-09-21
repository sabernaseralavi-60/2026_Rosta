# SABER Innovation & Learning Platform (SILP)

> اکوسیستمی که دانشجو را از **مصرف‌کنندهٔ دانش** به **تولیدکنندهٔ ارزش** تبدیل می‌کند.

---

## وضعیت پروژه

| مرحله | وضعیت |
|-------|-------|
| سند چشم‌انداز (v1) | ✅ [`CLAUDE.md`](CLAUDE.md) |
| **سند مشخصات محصول (PRD v2)** | ✅ [`docs/prd/`](docs/prd/) |
| پیاده‌سازی | ⏳ شروع نشده — مرحلهٔ M0 |

---

## سند مشخصات

PRD در ۱۵ سند نوشته شده است. نقطهٔ شروع:
**[`docs/prd/00-index-and-decisions.md`](docs/prd/00-index-and-decisions.md)**

| # | سند | موضوع |
|---|-----|-------|
| 00 | [فهرست و تصمیمات](docs/prd/00-index-and-decisions.md) | تصمیمات قفل‌شده، واژگان یکدست |
| 01 | [چشم‌انداز و پرسوناها](docs/prd/01-vision-personas.md) | ۵ پرسونا، معیارهای موفقیت، ریسک‌ها |
| 02 | [نیازمندی‌های عملکردی](docs/prd/02-functional-requirements.md) | ۵۷ نیازمندی با معیار پذیرش |
| 03 | [معماری اطلاعات](docs/prd/03-information-architecture.md) | نقشهٔ کامل صفحات |
| 04 | [مدل داده](docs/prd/04-data-model.md) | ۷۰ جدول PostgreSQL |
| 05 | [مشخصات API](docs/prd/05-api-specification.md) | قرارداد کامل endpointها |
| 06 | [نقش‌ها و مجوزها](docs/prd/06-roles-permissions.md) | ماتریس RBAC |
| 07 | [گردش‌کارها](docs/prd/07-workflows.md) | ماشین‌های حالت، همزمانی |
| 08 | [موتور توصیه‌گر](docs/prd/08-recommendation-engine.md) | الگوریتم با فرمول دقیق |
| 09 | [گیمیفیکیشن](docs/prd/09-gamification.md) | امتیاز، سطح، نشان |
| 10 | [سیستم طراحی](docs/prd/10-design-system.md) | رنگ، تایپوگرافی، RTL، اجزا |
| 11 | [نیازمندی‌های غیرعملکردی](docs/prd/11-non-functional.md) | امنیت، کارایی، حریم خصوصی |
| 12 | [معماری و استقرار](docs/prd/12-architecture-deployment.md) | Docker، CI/CD، عملیات |
| 13 | [نقشهٔ راه](docs/prd/13-roadmap.md) | ۸ مرحله، ~۱۲ هفته |
| 14 | [پیوست‌ها](docs/prd/14-appendices.md) | داده‌های اولیه، واژه‌نامه |

---

## پشتهٔ فنی

```
Backend    Python 3.12 · FastAPI · SQLAlchemy 2.0 (async) · Alembic
Database   PostgreSQL 16 · Redis
Frontend   Next.js 15 (App Router) · TypeScript · Tailwind CSS v4
Storage    S3-compatible (MinIO / ابر آروان)
Jobs       ARQ
Deploy     Docker Compose · Nginx · VPS ایران
```

دلیل هر انتخاب در [تصمیمات قفل‌شده](docs/prd/00-index-and-decisions.md#تصمیمات-قفلشدهٔ-معماری-locked-decisions) آمده است.

---

## شروع کار (پس از مرحلهٔ M0)

```bash
git clone <repo> && cd silp
make setup     # کپی .env، ساخت ایمیج، مهاجرت، داده‌های نمونه
make dev       # بالا آوردن همه چیز
```

| سرویس | آدرس |
|-------|------|
| وب | http://localhost:3000 |
| API | http://localhost:8000 |
| مستندات API | http://localhost:8000/docs |
| MinIO | http://localhost:9001 |
| ایمیل توسعه | http://localhost:8025 |

در محیط توسعه، کد OTP همیشه `111111` است.

---

## قواعد مشارکت

۱. هر تغییر باید به یک شناسهٔ نیازمندی اشاره کند: `FR-PRJ-04`، `NFR-06`.
۲. اول تست را از معیارهای پذیرش بنویس، سپس کد را.
۳. هر endpoint جدید نیازمند تست مجوز (۴۰۳) است.
۴. اگر سند ناقص بود، یک ADR در `docs/adr/` بنویس و سند را به‌روز کن — حدس نزن.
۵. قرارداد کامیت: `feat(prj): add application flow — FR-PRJ-04`

جزئیات کامل در [§11.5 قابلیت نگهداری](docs/prd/11-non-functional.md).

---

## مخاطب این سامانه

| گروه | چه می‌گیرد |
|------|-----------|
| دانشجوی درس | مسیر روشن هفتگی، پروژهٔ واقعی به‌جای تمرین |
| دانشجوی پژوهشی | مسیر ۴ سطحی از مرور ادبیات تا مقالهٔ Q1 |
| کارآفرین دانشجو | پروژهٔ آماده با امکان درآمد، بدون نیاز به سرمایه |
| استاد | دید یک‌نگاهی به اینکه چه کسی نیاز به کمک دارد |
| کاربر عمومی | دسترسی به محتوای آموزشی بدون ثبت‌نام دانشگاهی |
