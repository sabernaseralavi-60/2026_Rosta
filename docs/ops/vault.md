# راهنمای Vault شخصی

Vault یک پوشهٔ Markdown روی **رایانهٔ خودتان** است (سازگار با Obsidian). محتوای سایت را
در آن می‌نویسید، دادهٔ سایت را در آن می‌بینید و پیام گروهی را از آن می‌فرستید.
**در Git و GitHub نمی‌رود.** تصمیم‌ها و دلایل: [ADR-0030](../adr/0030-vault-content-engine-and-public-intake.md).

## راه‌اندازی (یک‌بار)

از پوشهٔ `apps/api`، با همان متغیرهای محیطی که سرور API دارد (`DATABASE_URL` و…):

```
python -m silp.scripts.vault --vault D:\SILP-Vault init
set SILP_VAULT=D:\SILP-Vault        # تا دیگر --vault نخواهد
```

`init` پوشه‌ها (`00_Inbox` … `99_Archive`)، یک `README.md` و دو قالب (`12_Content/_template.md`،
`14_AI/broadcasts/_template.md`) می‌سازد و **هیچ فایل موجودی را بازنویسی نمی‌کند**.
نمونهٔ آماده: `docs/vault-sample/`.

## نوشتن و انتشار محتوا

یک فایل در `12_Content/` بسازید (قالب را کپی کنید):

```
---
title: چرا مدل چهارمرحله‌ای هنوز زنده است؟
kind: article          # article | book-summary | paper-summary | example | case-study | dataset-note
status: published      # draft (پیش‌فرض) = منتشر نمی‌شود
access: public         # public | registered | student | member | premium
topics: [برنامه‌ریزی حمل‌ونقل]
skills: [مدل‌سازی تقاضا]
course: Transportation Planning
date: 2026-09-28
cover: research        # hero | learn | research | solve | collab | agri  یا نشانی https
slug: four-step-model  # نشانی پایدار؛ بعد از انتشار عوضش نکنید
---
متن با Markdown. فرمول: $x^2$ درون‌خطی، و $$T = \beta_0 + \beta_1 x$$ بلوکی.
```

```
python -m silp.scripts.vault publish            # پیش‌نمایش: چه چیزی تازه/به‌روز/آرشیو می‌شود
python -m silp.scripts.vault publish --apply    # انتشار واقعی
```

- اجرای دوباره روی Vault دست‌نخورده هیچ نوشتنی ندارد (`sha256` فایل).
- یادداشت خراب فقط خودش رد می‌شود؛ بقیه منتشر می‌شوند و پیام فارسیِ علت را می‌بینید.
- فایلی که پاک شود **آرشیو** می‌شود (برگشت‌پذیر)، نه حذف.
- فایل‌ها و پوشه‌های شروع‌شده با `_` یا `.` نادیده گرفته می‌شوند.
- سطح دسترسی `member` و `premium` تا فعال‌شدن عضویت فقط برای کادر آموزشی باز است.

## انتشار روی سرور جدا از رایانه‌تان (`push`)

`publish` به دیتابیس می‌رسد؛ وقتی سایت روی سرور است و Vault روی رایانهٔ شما، از API استفاده کنید
([ADR-0031](../adr/0031-vault-upload-api-and-api-tokens.md)).

**یک‌بار، روی سرور** (با همان متغیرهای محیطی API؛ مالک باید نقش ADMIN داشته باشد):

```
python -m silp.scripts.api_token create --mobile 09121234567 --name "رایانهٔ خانه"
```

توکن `silp_pat_…` فقط همین‌جا نمایش داده می‌شود. `list` و `revoke <شناسه>` هم هست؛ اگر رایانه‌تان
گم یا آلوده شد، ابطالش یک دستور است. **`--days 90`** توکن را منقضی می‌کند.

**هر بار، روی رایانه‌تان** (تنظیمات سرور و دیتابیس لازم نیست):

```
set SILP_API_URL=https://silp.example.ir
set SILP_API_TOKEN=silp_pat_…
python -m silp.scripts.vault push            # پیش‌نمایش
python -m silp.scripts.vault push --apply    # انتشار واقعی
```

- خروجی و قواعد همان `publish` است (بی‌اثر در تکرار، آرشیو فایل ناپدیدشده، خطای هر یادداشت).
- نشانی باید `https` باشد (فقط `localhost` استثناست)؛ توکن را در خط فرمان ندهید، در متغیر محیطی بماند.
- `--keep-missing` آرشیو را خاموش می‌کند؛ اگر پوشهٔ `12_Content` پیدا نشود خودبه‌خود خاموش است.
- `export` و `broadcast` هنوز فقط روی رایانه‌ای کار می‌کنند که به دیتابیس می‌رسد.

## دیدن دادهٔ سایت در Vault

```
python -m silp.scripts.vault export                  # همه
python -m silp.scripts.vault export --only inbox     # فقط درخواست‌های ورودی
```

می‌سازد: `02_Students/`، `05_Courses/`، `04_Projects/`، `00_Inbox/` (مسئله و همکاری‌های
تازه با کد پیگیری) و `DASHBOARD.md`. همه `generated: true` دارند و با هر اجرا بازنویسی
می‌شوند؛ **یادداشت شخصی‌تان را کنارشان بنویسید، نه داخلشان.** کد ملی صادر نمی‌شود.

## پیام گروهی

فایلی در `14_AI/broadcasts/`:

```
---
title: یادآوری آزمون این هفته
audience: students     # students | all | offering:<شناسه> | user:<موبایل>
---
آزمون این هفته تا پنجشنبه باز است.
```

```
python -m silp.scripts.vault broadcast 14_AI/broadcasts/پیام.md          # پیش‌نمایش: فقط شمار مخاطب
python -m silp.scripts.vault broadcast 14_AI/broadcasts/پیام.md --send   # ارسال
```

- پیش از ارسال به همهٔ دانشجویان، یک بار با `audience: user:09…` (شمارهٔ خودتان) امتحان کنید.
- **اجرای دوبارهٔ همان فایل پیام دوم نمی‌سازد.** متن را عوض کنید تا پیام تازه‌ای باشد.
- پیامک ندارد. کانال‌ها همان ترجیح هر کاربر است (داخل سامانه، ایمیل، Push…).
- پیام در صف Outbox می‌نشیند و کارگر ارسال می‌کند؛ ردّ ارسال‌ها در `14_AI/broadcast-log.md`.

## عکس‌ها

عکس‌های سایت در `apps/web/public/photos/` هستند. برای عوض‌کردن هرکدام، فایلی هم‌نام (مثلاً
`hero.jpg`، حدود ۱۹۲۰ پیکسل پهنا، نسبت ۳:۲) بگذارید و ردیفش را در `credits.json` به‌روز کنید؛
صفحهٔ `/credits` از همان می‌خواند.
