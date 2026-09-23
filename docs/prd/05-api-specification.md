# ۰۵ — مشخصات API

قرارداد بین Backend و Frontend. پایه: `https://api.silp.ir/api/v1`

FastAPI به‌صورت خودکار OpenAPI تولید می‌کند؛ این سند **قرارداد مرجع** است که کد
باید با آن مطابقت داشته باشد، و از روی OpenAPI تولیدشده، تایپ‌های TypeScript
ساخته می‌شوند (`packages/shared`).

---

## ۵.۱ قراردادهای عمومی

### احراز هویت

```http
Authorization: Bearer <access_token>
```

### قالب پاسخ موفق

پاسخ **مستقیماً** بدنهٔ داده است، بدون پوشش اضافی:

```json
{ "id": "018f...", "title_fa": "..." }
```

### قالب فهرست صفحه‌بندی‌شده

```json
{
  "items": [ … ],
  "total": 142,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

پارامترها: `?page=1&page_size=20` (حداکثر ۱۰۰). برای فهرست‌های پرترافیک
(اعلان، دفتر امتیاز) از **مکان‌نمای کرسری** استفاده می‌شود:
`?cursor=<opaque>&limit=20` با پاسخ `{ "items": [...], "next_cursor": "..." }`.

### قالب خطا

```json
{
  "error": {
    "code": "PROJECT_CAPACITY_FULL",
    "message": "ظرفیت این پروژه تکمیل شده است.",
    "details": { "capacity": 5, "current": 5 },
    "trace_id": "018f2a..."
  }
}
```

**قواعد خطا:**
- `code` ثابت، انگلیسی، SCREAMING_SNAKE — برای منطق کلاینت.
- `message` فارسی، قابل نمایش مستقیم به کاربر، بدون اصطلاح فنی.
- `trace_id` همیشه حاضر — کاربر می‌تواند به پشتیبانی بدهد.
- خطای اعتبارسنجی `422` شامل `details.fields` با کلید نام فیلد.

### کدهای وضعیت

| کد | کاربرد |
|----|--------|
| `200` | موفق |
| `201` | ساخته شد (با هدر `Location`) |
| `204` | موفق بدون بدنه |
| `400` | درخواست نادرست |
| `401` | احراز هویت نشده / توکن منقضی |
| `403` | احراز شده ولی بدون مجوز |
| `404` | یافت نشد (یا بدون مجوز دیدن — §11) |
| `409` | تعارض وضعیت (مثلاً ثبت‌نام تکراری) |
| `422` | خطای اعتبارسنجی |
| `429` | محدودیت نرخ — با هدر `Retry-After` |
| `500` | خطای سرور |

### Idempotency

همهٔ `POST`هایی که اثر جانبی دارند (پرداخت، ثبت امتیاز، ارسال تحویل‌دادنی)
هدر `Idempotency-Key: <uuid>` را می‌پذیرند و تا ۲۴ ساعت پاسخ یکسان برمی‌گردانند.

### محدودیت نرخ

| دسته | محدودیت |
|------|---------|
| `POST /auth/otp/request` | ۳ در ۱۰ دقیقه به‌ازای شماره، ۱۰ در ساعت به‌ازای IP |
| `POST /auth/*` | ۲۰ در دقیقه به‌ازای IP |
| نوشتن عمومی | ۶۰ در دقیقه به‌ازای کاربر |
| خواندن | ۳۰۰ در دقیقه به‌ازای کاربر |

---

## ۵.۲ احراز هویت — `/auth`

| متد | مسیر | توضیح |
|-----|------|-------|
| `POST` | `/auth/otp/request` | درخواست کد یک‌بارمصرف |
| `POST` | `/auth/otp/verify` | تأیید کد و دریافت توکن |
| `POST` | `/auth/login` | ورود با رمز عبور |
| `POST` | `/auth/refresh` | تمدید توکن (چرخشی) |
| `POST` | `/auth/logout` | خروج از نشست جاری |
| `GET` | `/auth/sessions` | فهرست نشست‌های فعال |
| `DELETE` | `/auth/sessions/{id}` | قطع یک نشست |
| `POST` | `/auth/password` | تنظیم یا تغییر رمز |
| `POST` | `/auth/email/verify/request` | ارسال لینک تأیید ایمیل |
| `POST` | `/auth/email/verify/confirm` | تأیید ایمیل با توکن |

**`POST /auth/otp/request`**
```jsonc
// درخواست
{ "destination": "09121234567", "channel": "SMS", "purpose": "LOGIN" }
// پاسخ 200
{ "challenge_id": "018f...", "expires_in": 120, "resend_after": 60,
  "masked_destination": "0912***4567" }
// خطاها: 429 OTP_RATE_LIMITED، 422 INVALID_DESTINATION
```

**`POST /auth/otp/verify`**
```jsonc
// درخواست
{ "challenge_id": "018f...", "code": "482913" }
// پاسخ 200
{ "access_token": "eyJ…", "refresh_token": "…", "token_type": "Bearer",
  "expires_in": 900,
  "user": { "id": "018f…", "display_name": null, "roles": ["STUDENT"],
            "onboarding_state": "BASIC_INFO_REQUIRED" } }
// خطاها: 400 OTP_INVALID، 400 OTP_EXPIRED، 429 OTP_TOO_MANY_ATTEMPTS
```

`onboarding_state` تعیین می‌کند کلاینت کاربر را به کدام صفحه بفرستد:
`BASIC_INFO_REQUIRED` → `SURVEY_INCOMPLETE` → `COMPLETE`.

**`POST /auth/refresh`**
```jsonc
{ "refresh_token": "…" }
// پاسخ: جفت توکن جدید. توکن قدیمی بلافاصله باطل می‌شود.
// خطای 401 TOKEN_REUSE_DETECTED ⇒ کل خانواده باطل شد، ورود مجدد لازم است.
```

---

## ۵.۳ نیمرخ — `/me`, `/profiles`

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/me` | اطلاعات کاربر جاری + نقش‌ها + وضعیت ورود اولیه |
| `PATCH` | `/me/profile` | به‌روزرسانی جزئی اطلاعات پایه |
| `GET` | `/me/survey` | وضعیت کامل ارزیابی نیمرخ |
| `PATCH` | `/me/survey/skills` | ثبت گام ۱ |
| `PATCH` | `/me/survey/assets` | ثبت گام ۲ |
| `PATCH` | `/me/survey/interests` | ثبت گام ۳ |
| `PATCH` | `/me/survey/preferences` | ثبت گام ۴ |
| `GET` | `/me/points` | دفتر کل امتیاز شخصی (کرسری) |
| `GET` | `/me/points/summary` | امتیاز کل، سطح، امتیاز نیم‌سال و ۵ ردیف اخیر (برای Toast) |
| `GET` | `/me/badges` | نشان‌های کسب‌شده و قفل‌شده |
| `POST` | `/me/badges/seen` | جشن نشان دیده شد (§9.10) |
| `GET` | `/me/dashboard` | داشبورد دانشجو در یک درخواست (FR-DASH-01) |
| `GET` | `/me/learning-score/{offering_id}` | نمرهٔ یادگیری من با چهار مؤلفه (§9.6) |
| `GET` | `/me/certificates` | گواهی‌ها |
| `PATCH` | `/me/settings` | حریم خصوصی و اعلان |
| `POST` | `/me/avatar` | دریافت URL آپلود آواتار |
| `GET` | `/profiles/{username}` | نیمرخ عمومی (بدون احراز هویت) |

**`GET /me` — پاسخ**
```jsonc
{
  "id": "018f…",
  "mobile": "0912***4567",
  "email": "s@example.com",
  "email_verified": true,
  "username": "maryam-k",
  "profile": {
    "first_name": "مریم", "last_name": "کریمی",
    "avatar_url": "https://…",
    "university": { "id": "…", "title_fa": "دانشگاه شهید باهنر کرمان" },
    "field_of_study": "مهندسی عمران",
    "degree_level": "BACHELOR",
    "work_style": "TEAM", "primary_goal": "LEARNING", "weekly_hours": 10
  },
  "roles": [{ "code": "STUDENT", "scope_type": "GLOBAL", "scope_id": null }],
  "onboarding": { "state": "SURVEY_INCOMPLETE", "completed_steps": 2, "total_steps": 4 },
  "points": { "total": 340, "level": 4, "next_level_at": 459 },
  "unread_notifications": 3
}
```

**`PATCH /me/survey/skills`**
```jsonc
// درخواست — ارسال جزئی مجاز است
{ "skills": [ { "skill_id": "018f…", "level": 4 },
              { "skill_id": "018f…", "level": 2 } ] }
// پاسخ 200
{ "completed_steps": 1,
  "preview_recommendations": [ { "project_id": "…", "title_fa": "…", "match_score": 78.5 } ] }
```

> `preview_recommendations` همان «لحظهٔ طلایی» §01 است — سرور بلافاصله پس از گام ۱
> سه پیشنهاد برمی‌گرداند.

---

## ۵.۳.۱ عمومی — `/public`

بدون احراز هویت. برای صفحهٔ اصلی و ویترین‌ها.

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/public/stats` | آمار زندهٔ سامانه برای صفحهٔ اصلی |
| `GET` | `/public/courses` | ویترین دروس عمومی |
| `GET` | `/public/projects` | ویترین پروژه‌های باز (بدون امتیاز تطابق) |
| `GET` | `/public/certificates/{code}` | راستی‌آزمایی گواهی |

**`GET /public/stats`** — با `Cache-Control: public, max-age=300`
```jsonc
{
  "students": 214,
  "active_projects": 38,
  "completed_milestones": 461,
  "research_outputs": 12,
  "verified_revenue_rial": 460000000,
  "active_courses": 4
}
```

> اگر عددی صفر باشد، کلاینت آن را نمایش نمی‌دهد (§10.10). سرور عدد واقعی
> برمی‌گرداند و تصمیم نمایش با رابط کاربری است.

**`GET /public/certificates/{code}`**
```jsonc
// 200 → { "valid": true, "holder_name": "مریم کریمی",
//         "title_fa": "تکمیل پروژهٔ …", "issued_at": "…", "issuer": "…" }
// 404 → گواهی یافت نشد یا باطل شده است
```

---

## ۵.۴ طبقه‌بندی‌ها — `/taxonomy`

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/taxonomy/skills` | فهرست مهارت‌ها (کش عمومی ۱ ساعته) |
| `GET` | `/taxonomy/assets` | فهرست امکانات |
| `GET` | `/taxonomy/interests` | فهرست علاقه‌ها |
| `GET` | `/taxonomy/universities?q=` | جستجوی دانشگاه |
| `GET` | `/taxonomy/terms` | نیم‌سال‌ها، با علامت جاری |

این مسیرها با `Cache-Control: public, max-age=3600` پاسخ می‌دهند.

---

## ۵.۵ آموزش — `/courses`, `/offerings`

| متد | مسیر | نقش | توضیح |
|-----|------|-----|-------|
| `GET` | `/courses` | عمومی | ویترین دروس |
| `GET` | `/courses/{slug}` | عمومی | جزئیات درس |
| `GET` | `/offerings` | STUDENT | ارائه‌های قابل ثبت‌نام |
| `GET` | `/offerings/{id}` | ثبت‌نام‌شده | نمای کلی ارائه |
| `POST` | `/offerings/{id}/enroll` | STUDENT | ثبت‌نام |
| `DELETE` | `/offerings/{id}/enroll` | STUDENT | انصراف |
| `GET` | `/offerings/{id}/weeks` | ثبت‌نام‌شده | فهرست هفته‌ها |
| `GET` | `/offerings/{id}/weeks/{n}` | ثبت‌نام‌شده | محتوای هفته |
| `GET` | `/offerings/{id}/grades` | ثبت‌نام‌شده | کارنامهٔ من |
| `GET` | `/offerings/{id}/announcements` | ثبت‌نام‌شده | اعلانات |
| `POST` | `/resources/{id}/progress` | ثبت‌نام‌شده | ثبت پیشرفت مطالعه |
| `GET` | `/resources/{id}/download` | ثبت‌نام‌شده | URL دانلود موقت |
| `GET` | `/offerings/mine` | STUDENT | دروس من با نوار پیشرفت |
| `GET` | `/materials/{id}/download` | **بسته به سطح** | URL دانلود محتوای کتابخانه |
| `GET` | `/materials/tiers` | عمومی | متن فارسی سطوح دسترسی |

**`GET /materials/{id}/download` — دروازهٔ اشتراک (ADR-0009)**

```jsonc
// 200 → { "download_url": "…", "expires_in": 900, "original_name": "…" }
// 402 SUBSCRIPTION_REQUIRED  — محتوا هست، این کاربر حق دیدنش را نخریده.
//     details: { "course_slug": "road-safety-modeling" }
// 403 ENROLLMENT_REQUIRED    — سطح ENROLLED؛ فروختنی نیست، اشتراک بازش نمی‌کند.
```

**سنجش دسترسی همراه هر ماده می‌آید.** `GET /courses/{slug}` و
`GET /offerings/{id}/weeks/{n}` برای هر محتوا یک شیء `access` برمی‌گردانند:

```jsonc
{ "allowed": false, "tier": "SUBSCRIBER", "reason": null,
  "blocker": "SUBSCRIPTION",
  "note_fa": "برای دیدن این محتوا اشتراک بگیرید — یا در همین درس ثبت‌نام کنید." }
```

`note_fa` را **سرور** می‌سازد و مستقیماً نمایش داده می‌شود؛ کلاینت هرگز
متن قفل را خودش نمی‌نویسد. محتوای قفل‌شده از فهرست حذف نمی‌شود — فقط
`external_url` و لینک دانلودش بسته است.

---

## ۵.۵.۱ اشتراک — `/subscriptions` (ADR-0009)

| متد | مسیر | نقش | توضیح |
|-----|------|-----|-------|
| `GET` | `/subscriptions/plans` | عمومی | طرح‌ها با قیمت آمادهٔ نمایش |
| `GET` | `/subscriptions` | کاربر | اشتراک‌های من |
| `POST` | `/subscriptions` | کاربر | ثبت درخواست (وضعیت `PENDING`) |
| `DELETE` | `/subscriptions/{id}` | کاربر | لغو |
| `GET` | `/subscriptions/pending` | SUPPORT | درخواست‌های در انتظار تأیید |
| `POST` | `/subscriptions/{id}/activate` | SUPPORT | تأیید پرداخت بیرونی |
| `POST` | `/subscriptions/grant` | SUPPORT | ساخت و فعال‌سازی در یک گام |

**پرداخت درون سامانه انجام نمی‌شود** (§02). `POST /subscriptions` یک
رسید «در انتظار» می‌سازد و `activate` آن را فعال می‌کند. وقتی درگاه
آمد، فقط `activate` یک صداکنندهٔ تازه پیدا می‌کند.

**`POST /offerings/{id}/enroll`**
```jsonc
{ "enrollment_code": "TRP1404" }   // اختیاری
// 201 → { "enrollment_id": "…", "status": "ACTIVE" }
// 409 ALREADY_ENROLLED | 403 ENROLLMENT_CODE_INVALID | 409 OFFERING_FULL
```

**`GET /offerings/{id}/weeks/{n}` — پاسخ**
```jsonc
{
  "week_number": 5,
  "title_fa": "مدل‌سازی تقاضای سفر",
  "objectives": ["درک مدل چهارمرحله‌ای", "کار با ماتریس مبدأ-مقصد"],
  "published_at": "2026-03-01T08:00:00Z",
  "resources": [
    { "id": "…", "kind": "PDF", "title_fa": "جزوهٔ هفتهٔ ۵",
      "size_bytes": 2400000, "is_downloadable": true,
      "progress": { "status": "IN_PROGRESS", "percent": 40 } }
  ],
  "quiz": { "id": "…", "title_fa": "آزمون هفتهٔ ۵", "duration_min": 30,
            "opens_at": "…", "closes_at": "…",
            "my_attempts": 0, "max_attempts": 2, "state": "AVAILABLE" },
  "qa_thread_count": 7
}
```

`quiz.state` مقادیر: `NOT_OPEN` / `AVAILABLE` / `IN_PROGRESS` / `EXHAUSTED` / `CLOSED`.
کلاینت هرگز نباید این منطق را خودش محاسبه کند.

---

## ۵.۶ آزمون — `/quizzes`, `/attempts`

| متد | مسیر | نقش | توضیح |
|-----|------|-----|-------|
| `GET` | `/quizzes/{id}` | دانشجو | فراداده (بدون سؤالات) |
| `POST` | `/quizzes/{id}/attempts` | دانشجو | شروع تلاش |
| `GET` | `/attempts/{id}` | صاحب تلاش | سؤالات + پاسخ‌های ذخیره‌شده + زمان باقی |
| `PUT` | `/attempts/{id}/answers/{qid}` | صاحب تلاش | ذخیرهٔ پاسخ (بی‌اثر تکراری) |
| `POST` | `/attempts/{id}/sync` | صاحب تلاش | همگام‌سازی دسته‌ای پس از آفلاین |
| `POST` | `/attempts/{id}/submit` | صاحب تلاش | ارسال نهایی |
| `GET` | `/attempts/{id}/result` | صاحب تلاش | نتیجه |
| `POST` | `/attempts/{id}/appeal` | صاحب تلاش | اعتراض به نمره |
| `POST` | `/attempts/{id}/integrity` | صاحب تلاش | ثبت رویداد تمامیت |
| `GET` | `/quizzes/offering/{id}` | دانشجو | آزمون‌های یک ارائه با وضعیت هر کدام |

**ناحیهٔ استاد** زیر `/teach` است و قلمرو همهٔ مجوزهایش **ارائه**
(ADR-0010):

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET/POST` | `/teach/offerings/{id}/quizzes` | فهرست و ساخت آزمون |
| `GET/PUT/DELETE` | `/teach/quizzes/{id}` | آزمون با کلید پاسخ |
| `POST` | `/teach/quizzes/{id}/publish` · `/close` · `/publish-results` | چرخهٔ حیات |
| `POST/PUT/DELETE` | `/teach/quizzes/{id}/questions[/{qid}]` | ویرایشگر سؤال |
| `POST` | `/teach/quizzes/{id}/questions/reorder` | ترتیب سؤال‌ها |
| `GET/POST` | `/teach/question-bank` | بانک سؤال |
| `POST` | `/teach/quizzes/{id}/questions/from-bank` · `/random` | کپی و انتخاب تصادفی |
| `GET` | `/teach/quizzes/{id}/attempts` | تلاش‌های این آزمون |
| `GET` | `/teach/quizzes/{id}/grading-queue` | صف تصحیح، **بر اساس سؤال** |
| `PUT` | `/teach/quizzes/{id}/attempts/{aid}/answers/{qid}` | ثبت یا بازنویسی نمره |
| `POST` | `/teach/quizzes/{id}/attempts/{aid}/finalize` · `/void` | پایان تصحیح، ابطال |
| `GET` | `/teach/quizzes/{id}/question-stats` | ضریب دشواری و تمیز |
| `GET` | `/teach/quizzes/{id}/appeals` | اعتراض‌های باز |
| `POST` | `/teach/appeals/{id}/resolve` | رسیدگی |
| `POST` | `/teach/attempts/close-expired` | اجرای دستی کار پس‌زمینه |

**`POST /quizzes/{id}/attempts` — پاسخ ۲۰۱**
```jsonc
{
  "attempt_id": "018f…",
  "server_time": "2026-03-01T10:00:00Z",
  "expires_at": "2026-03-01T10:30:00Z",
  "seconds_remaining": 1800,
  "question_count": 20,
  "total_points": 20
}
```

**`GET /attempts/{id}` — پاسخ**
```jsonc
{
  "attempt_id": "018f…",
  "server_time": "2026-03-01T10:05:12Z",
  "seconds_remaining": 1488,
  "questions": [
    { "id": "…", "kind": "SINGLE_CHOICE", "body": "کدام مدل …؟",
      "points": 1,
      "payload": { "options": [ {"id":"a","text":"…"}, {"id":"b","text":"…"} ] },
      "my_answer": { "selected": ["a"] },
      "is_flagged": false }
  ]
}
```

> **الزام امنیتی:** میدان `correct` هرگز در `payload` سؤالات یک تلاش فعال ارسال
> نمی‌شود. این باید در تست خودکار بررسی شود.

**`PUT /attempts/{id}/answers/{qid}`**
```jsonc
{ "response": { "selected": ["b"] }, "is_flagged": true,
  "client_ts": "2026-03-01T10:05:10Z" }
// 200 → { "saved_at": "2026-03-01T10:05:11Z", "seconds_remaining": 1489 }
// 409 ATTEMPT_EXPIRED | 409 ATTEMPT_ALREADY_SUBMITTED
```

**`POST /attempts/{id}/sync`** — برای بازیابی پس از قطعی اینترنت:
```jsonc
{ "answers": [ { "question_id": "…", "response": {...}, "client_ts": "…" } ] }
// سرور جدیدترین client_ts را برای هر سؤال می‌پذیرد.
// اگر مهلت گذشته باشد: 409 با ثبت پاسخ‌های قبل از expires_at.
```

**`POST /attempts/{id}/submit`**
```jsonc
{ "confirm_unanswered": 2 }   // کلاینت تعداد بی‌پاسخ را تأیید می‌کند
// 200 → { "status": "GRADED", "auto_score": 16.5, "is_provisional": true,
//         "total_points": 20, "result_available": false }
```

> **`GET /attempts/{id}/result`** علاوه بر نمره، `auto_closed` هم
> می‌دهد: تلاشی که کار پس‌زمینه بسته با تلاشی که دانشجو فرستاده یکی
> نیست (ADR-0011). `class_average` زیر سه تلاش `null` می‌ماند تا از
> روی میانگین، نمرهٔ بقیه قابل حدس نباشد.

---

## ۵.۷ پروژه — `/projects`

| متد | مسیر | نقش | توضیح |
|-----|------|-----|-------|
| `GET` | `/projects` | همه | فهرست با فیلتر و مرتب‌سازی |
| `GET` | `/projects/recommended` | دانشجو | **پیشنهادهای شخصی با دلیل** |
| `GET` | `/projects/{id}` | همه | جزئیات + تطابق من |
| `POST` | `/projects` | LEAD+ | ساخت پروژه |
| `PATCH` | `/projects/{id}` | مدیر پروژه | ویرایش |
| `GET` | `/projects/mine` | کاربر | پروژه‌هایی که مدیر یا عضوشانم (شامل پیش‌نویس) |
| `POST` | `/projects/{id}/publish` | مدیر پروژه | انتشار (DRAFT→OPEN) |
| `POST` | `/projects/{id}/start` | مدیر پروژه | شروع کار (OPEN→IN_PROGRESS) |
| `POST` | `/projects/{id}/pause` | مدیر پروژه | توقف موقت، با ذکر دلیل |
| `POST` | `/projects/{id}/resume` | مدیر پروژه | از سرگیری (PAUSED→OPEN) |
| `POST` | `/projects/{id}/cancel` | مدیر پروژه | لغو، با ذکر دلیل |
| `POST` | `/projects/{id}/applications` | دانشجو | درخواست پیوستن |
| `GET` | `/projects/{id}/applications` | مدیر پروژه | فهرست درخواست‌ها |
| `GET` | `/applications/mine` | دانشجو | درخواست‌های من |
| `POST` | `/applications/{id}/decide` | مدیر پروژه | تصمیم |
| `DELETE` | `/applications/{id}` | متقاضی | انصراف از درخواست |
| `GET` | `/projects/{id}/team` | عضو | اعضای تیم |
| `DELETE` | `/projects/{id}/team/{uid}?reason=…` | مدیر پروژه | حذف عضو، با ذکر دلیل |
| `POST` | `/projects/{id}/leave` | عضو | ترک تیم |
| `GET/POST` | `/projects/{id}/milestones` | عضو / مدیر | مراحل |
| `PATCH/DELETE` | `/milestones/{id}` | مدیر پروژه | ویرایش و حذف مرحله |
| `GET/POST` | `/milestones/{id}/deliverables` | عضو | تاریخچهٔ نسخه‌ها و ارسال |
| `POST` | `/deliverables/{id}/review` | مدیر پروژه | بررسی و بازخورد |
| `GET` | `/projects/{id}/review-queue` | مدیر پروژه | صف بررسی پروژه |
| `GET/POST` | `/projects/{id}/tasks` | عضو | تخته وظایف |
| `PATCH/DELETE` | `/projects/{id}/tasks/{task_id}` | عضو | ویرایش و حذف وظیفه |
| `GET/POST` | `/projects/{id}/announcements` | عضو / مدیر | اعلان‌های پروژه |
| `GET/POST` | `/projects/{id}/discussion` | عضو | گفتگوی تیمی |
| `DELETE` | `/projects/{id}/discussion/{message_id}` | نویسنده / مدیر | حذف پیام |
| `GET` | `/projects/{id}/activity` | عضو | جریان فعالیت پروژه |
| `POST` | `/projects/{id}/complete` | مدیر پروژه | بستن پروژه |
| `POST` | `/projects/{id}/reflection` | عضو | ثبت بازتاب |
| `POST` | `/recommendations/{project_id}/feedback` | دانشجو | بازخورد پیشنهاد |

**`GET /projects` — پارامترها**
```
?kind=A_VENTURE&status=OPEN&skill_id=…&work_style=TEAM
&difficulty_max=3&offering_id=…&q=خرما
&sort=match|newest|popular|deadline
&page=1&page_size=20
```

**`GET /projects/recommended` — پاسخ**
```jsonc
{
  "items": [
    {
      "project": { "id": "…", "title_fa": "فروش و بازاریابی خرمای صابر",
                   "kind": "A_VENTURE", "difficulty": 2,
                   "time_commitment_hpw": 8, "summary": "…" },
      "match_score": 86.4,
      "reasons": [
        { "type": "ASSET_MATCH",   "polarity": "POSITIVE",
          "text": "موتور داری و این پروژه به توزیع نیاز دارد" },
        { "type": "INTEREST_MATCH","polarity": "POSITIVE",
          "text": "به فروش و بازاریابی علاقهٔ زیاد نشان داده‌ای" },
        { "type": "SKILL_GAP",     "polarity": "WARNING",
          "text": "طراحی گرافیک لازم است که هنوز در سطح ۲ هستی — قابل یادگیری است" }
      ],
      "breakdown": { "skill": 72.0, "asset": 100.0, "interest": 95.0,
                     "availability": 80.0, "style": 100.0, "goal": 100.0 }
    }
  ],
  "profile_completeness": 0.75,
  "computed_at": "2026-03-01T10:00:00Z"
}
```

> `reasons` قابل نمایش مستقیم است. بک‌اند متن فارسی را تولید می‌کند تا منطق
> توضیح در یک جا بماند (§08).

**`POST /milestones/{id}/deliverables`**
```jsonc
{ "body": "گزارش مرحلهٔ اول …",
  "file_ids": ["018f…","018f…"],
  "links": ["https://github.com/…"] }
// 201 → { "id": "…", "version": 1, "status": "SUBMITTED" }
// 409 MILESTONE_NOT_OPEN | 403 NOT_TEAM_MEMBER
```

**`POST /deliverables/{id}/review`**
```jsonc
{ "decision": "APPROVED",           // APPROVED | CHANGES_REQUESTED | REJECTED
  "score": 18.5,
  "feedback": "کار خوبی بود، فقط …",
  "rubric_scores": { "completeness": 5, "quality": 4, "timeliness": 5 } }
// 200 → { "status": "APPROVED",
//         "points_awarded": [ { "category": "LEARNING", "amount": 50 } ] }
```

---

## ۵.۸ کارآفرینی، پژوهش، ایده، تیم

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET/POST` | `/ventures` | فهرست (`q`، `stage`، `looking_for_cofounder`) و ثبت کسب‌وکار — ثبت نیمرخ کامل می‌خواهد |
| `GET` | `/ventures/mine` | کسب‌وکارهایی که عضو فعال تیمشانم |
| `GET/PATCH/DELETE` | `/ventures/{id}` | جزئیات، ویرایش، حذف (فقط مرحلهٔ `IDEA`) — `readiness` و `totals` فقط برای اعضا و مدیران |
| `POST` | `/ventures/{id}/stage` | `ADVANCE`، `PAUSE`، `RESUME`، `CLOSE`؛ کمبود معیار ⇒ `409 STAGE_CRITERIA_NOT_MET` با `details.missing` |
| `GET/POST` | `/ventures/{id}/metrics` | فهرست با جمع کل و جمع هر عضو، و ثبت فعالیت یا فروش (عضو) |
| `GET/POST` | `/projects/{id}/metrics` | همان، برای پروژهٔ عملیاتی نوع A (FR-VEN-02) |
| `GET` | `/metrics/review-queue` | شاخص‌های در انتظاری که کاربر حق تأییدشان را دارد |
| `POST` | `/metrics/{id}/review` | `VERIFIED` یا `REJECTED` (رد با یادداشت) — نه برای ثبت خودِ کاربر |
| `DELETE` | `/metrics/{id}` | حذف ثبت در انتظار (ثبت‌کننده) |
| `POST` | `/ventures/{id}/leave` · `/members/{uid}/remove` | ترک تیم، حذف عضو با دلیل |
| `GET/POST` | `/ventures/{id}/invitations` | دعوت‌های باز و دعوت با نام کاربری (بنیان‌گذار) |
| `POST` | `/projects/{id}/invitations` | دعوت مستقیم به تیم پروژه (`project.application.decide`) |
| `GET` | `/me/invitations` | دعوت‌های باز من |
| `POST` | `/invitations/{id}/accept` · `/decline` | پاسخ؛ دعوت بسته یا منقضی ⇒ `409 INVITATION_CLOSED` |
| `DELETE` | `/invitations/{id}` | لغو دعوت (دعوت‌کننده) |
| `GET` | `/research/tracks` | وضعیت مسیر پژوهشی من |
| `POST` | `/research/tracks/{level}/submit` | ارسال تحویل‌دادنی سطح |
| `GET/POST` | `/research/topics` | بانک موضوع |
| `POST` | `/research/topics/{id}/reserve` | رزرو موضوع |
| `GET/POST` | `/research/outputs` | خروجی‌های پژوهشی |
| `GET/POST` | `/ideas` | بانک ایده — `sort=hot\|new\|top`، `status`، `category`، `tag`، `q`، `mine` |
| `GET` | `/ideas/categories` | هشت دستهٔ ثابت با عنوان فارسی |
| `GET/PATCH/DELETE` | `/ideas/{id}` | جزئیات با نظرها؛ ویرایش و حذف (نویسنده، ایدهٔ باز) |
| `POST/DELETE` | `/ideas/{id}/vote` | رأی و پس‌گرفتن؛ رأی دوباره ⇒ `409 DUPLICATE_VOTE`، رأی به ایدهٔ خود ⇒ ۴۰۹ |
| `POST` | `/ideas/{id}/comments` | نظر، یا پاسخ با `parent_id` (نخ یک‌سطحی) |
| `DELETE` | `/ideas/comments/{id}` | حذف نظر (نویسنده یا `idea.moderate`) |
| `POST` | `/ideas/{id}/archive` | بایگانی با دلیل (`idea.moderate`) |
| `POST` | `/ideas/{id}/promote` | ارتقا (`idea.promote`) — `PROJECT` با `project_kind`، یا `VENTURE` (نه برای ایدهٔ ناشناس) |
| `GET` | `/teams/search` | جستجوی هم‌تیمی |
| `GET/POST` | `/teams/openings` | آگهی نیاز به هم‌تیمی |
| `POST` | `/teams/openings/{id}/apply` | درخواست برای آگهی |
| `GET` | `/leaderboard` | رتبه‌بندی |

**`GET /teams/search` — پارامترها و پاسخ**
```
?skill_id=…&min_level=3&asset_id=…&interest_id=…&offering_id=…&university_id=…
&complement_project_id=…   ← مکمل تیم فعلی این پروژه
```
```jsonc
{ "items": [
    { "user": { "username": "ali-m", "display_name": "علی م.",
                "avatar_url": "…", "university": "…" },
      "top_skills": [ { "title_fa": "Python", "level": 5, "verified": true } ],
      "assets": ["لپ‌تاپ","دوربین"],
      "complement_score": 92.0,
      "complement_reason": "مهارت GIS را دارد که هیچ‌کس در تیم ندارد" } ] }
```

**`GET /leaderboard`**
```
?scope=GLOBAL|OFFERING|UNIVERSITY&scope_id=…&category=LEARNING&term_id=…&limit=10
```
```jsonc
{ "entries": [ { "rank": 1, "user": {…}, "total": "1240.00", "level": 8, "is_me": false } ],
  "growth":  [ /* بیشترین رشد ۳۰ روزه — §9.7 قاعدهٔ ۵ */ ],
  "me": { "rank": 34, "total": "340.00", "level": 4, "percentile": 62,
          "hidden": false, "excluded_reason": null } }
```

`excluded_reason`: `OPTED_OUT` (انصراف؛ رتبه‌اش را خودش می‌بیند) یا
`STAFF` (کادر آموزشی؛ در رقابت دانشجویان رتبه ندارد — [ADR-0012](../adr/0012-ledger-revisions-and-gamification-gaps.md)). صدک
برای جمع کمتر از ۵ نفر `null` است. رتبه‌بندی ارائه برای غیرعضو ۴۰۴ است.

---

## ۵.۹ فایل — `/files`

| متد | مسیر | توضیح |
|-----|------|-------|
| `POST` | `/files/upload-url` | دریافت URL آپلود مستقیم |
| `POST` | `/files/{id}/complete` | اعلام پایان آپلود |
| `GET` | `/files/{id}/download-url` | URL دانلود موقت |
| `DELETE` | `/files/{id}` | حذف نرم |

**`POST /files/upload-url`**
```jsonc
// درخواست
{ "original_name": "report.pdf", "content_type": "application/pdf",
  "size_bytes": 2400000, "purpose": "DELIVERABLE" }
// پاسخ 200
{ "file_id": "018f…",
  "upload_url": "https://s3…?X-Amz-Signature=…",
  "method": "PUT",
  "headers": { "Content-Type": "application/pdf" },
  "expires_in": 900 }
// 413 FILE_TOO_LARGE | 415 CONTENT_TYPE_NOT_ALLOWED
```

جریان: کلاینت `PUT` به `upload_url` → سپس `POST /files/{id}/complete` → سرور
اندازه و Magic Number را بررسی می‌کند و `scan_status` را در صف می‌گذارد.

---

## ۵.۱۰ اعلان — `/notifications`

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/notifications` | فهرست (کرسری) |
| `GET` | `/notifications/unread-count` | شمارندهٔ خوانده‌نشده |
| `POST` | `/notifications/{id}/read` | علامت خوانده‌شده |
| `POST` | `/notifications/read-all` | همه را خوانده‌شده کن |
| `GET/PUT` | `/notifications/preferences` | تنظیمات کانال — دسته ⇒ کانال‌ها؛ وضعیت هر کانال و ساعت آرام |
| `POST` | `/notifications/channels/{telegram\|eitaa}/link` | شروع پیوند: پیوند عمیق تلگرام، یا فرستادن کد به ایتا |
| `POST` | `/notifications/channels/eitaa/confirm` | تأیید کد ایتا |
| `DELETE` | `/notifications/channels/{channel}` | قطع پیوند |
| `GET` | `/notifications/stream` | **SSE** برای اعلان بی‌درنگ |
| `POST` | `/integrations/telegram/webhook` | وب‌هوک ربات؛ هدر `X-Telegram-Bot-Api-Secret-Token` |

`GET /notifications/stream` از Server-Sent Events استفاده می‌کند، نه WebSocket —
ساده‌تر، سازگارتر با پروکسی‌های ایرانی، و برای این کاربرد کافی است.

جریان دو رویداد دارد: `unread` با `{"count": n}` و `notification` با یک
اعلان کامل. هر ۱۰ دقیقه بسته می‌شود و کلاینت با توکن تازه دوباره وصل
می‌شود. کلاینت با `fetch` و هدر `Authorization` می‌خواند، نه `EventSource`
— توکن هرگز در نشانی نمی‌آید (ADR-0013).

---

## ۵.۱۱ استاد — `/teach`

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/teach/dashboard` | داشبورد استثنامحور |
| `GET` | `/teach/offerings` | ارائه‌های من |
| `PUT` | `/teach/offerings/{id}/weeks` | ساخت یا ویرایش هفته (کلید: شمارهٔ هفته) |
| `POST` | `/teach/weeks/{id}/publish` | انتشار (فوری یا زمان‌بندی‌شده) |
| `POST` | `/teach/offerings/{id}/copy-content` | کپی محتوا از ارائهٔ قبلی |
| `POST` | `/teach/offerings/{id}/weeks/{wid}/resources` | افزودن منبع هفته |
| `DELETE` | `/teach/resources/{id}` | حذف منبع |
| `POST` | `/teach/offerings/{id}/weeks/{wid}/materials` | بستن محتوای کتابخانه به هفته |
| `PUT` | `/teach/offerings/{id}/grading-policy` | وزن‌های نمره (مجموع = ۱۰۰) |
| `GET` | `/teach/offerings/{id}/students` | دانشجویان با پیشرفت و پرچم خطر |
| `POST` | `/teach/offerings/{id}/attendance` | ثبت گروهی حضور |
| `GET` | `/teach/offerings/{id}/gradebook` | دفتر نمره |
| `PATCH` | `/teach/enrollments/{id}/grade` | ثبت نمرهٔ نهایی |
| `GET` | `/teach/offerings/{id}/export` | خروجی Excel |
| `POST` | `/teach/quizzes` | ساخت آزمون |
| `POST` | `/teach/quizzes/{id}/questions` | افزودن سؤال |
| `POST` | `/teach/quizzes/{id}/questions/from-bank` | افزودن از بانک |
| `GET` | `/teach/quizzes/{id}/grading-queue` | **صف تصحیح بر اساس سؤال** |
| `POST` | `/teach/answers/{attempt_id}/{qid}/grade` | ثبت نمرهٔ تشریحی |
| `GET` | `/teach/quizzes/{id}/analytics` | تحلیل سؤال |
| `GET` | `/teach/review-queue` | صف واحد بررسی تحویل‌دادنی |
| `GET` | `/teach/offerings/{id}/learning-scores` | نمرهٔ یادگیری و نمرهٔ پیشنهادی (`LS × 0.2`) همهٔ دانشجویان — فقط خواندنی |
| `POST` | `/teach/enrollments/{id}/decide` | تأیید یا رد ثبت‌نام |

**`GET /teach/dashboard` — پاسخ**
```jsonc
{
  "needs_attention": {
    "deliverables_pending": { "count": 12, "oldest_days": 5 },
    "essays_pending":       { "count": 34, "oldest_days": 2 },
    "enrollment_requests":  { "count": 3 },
    "grade_appeals":        { "count": 1 },
    "projects_at_risk":     [ { "id": "…", "title_fa": "…", "health": "STALLED",
                                "days_inactive": 18 } ],
    "students_at_risk":     [ { "user_id": "…", "display_name": "…",
                                "reason": "۱۷ روز بدون فعالیت",
                                "offering_id": "…" } ]
  },
  "offerings": [ { "id": "…", "title_fa": "…", "students": 42,
                   "avg_progress": 0.63, "avg_quiz_score": 15.2 } ]
}
```

**`GET /teach/quizzes/{id}/grading-queue?question_id=…`** — پاسخ‌های همهٔ
دانشجویان به **یک سؤال**، به‌صورت ناشناس (اختیاری) برای کاهش سوگیری:
```jsonc
{ "question": { "id": "…", "body": "…", "points": 5, "payload": { "rubric": "…" } },
  "progress": { "graded": 12, "total": 42 },
  "answers": [ { "attempt_id": "…", "student_label": "دانشجوی ۱۳",
                 "response": { "text": "…" }, "current_score": null } ] }
```

---

## ۵.۱۲ مدیریت — `/admin`

| متد | مسیر | توضیح |
|-----|------|-------|
| `GET` | `/admin/metrics` | شاخص‌های کلان |
| `GET/PATCH` | `/admin/users` | مدیریت کاربران |
| `POST` | `/admin/users/{id}/roles` | اعطای نقش |
| `DELETE` | `/admin/users/{id}/roles/{code}` | سلب نقش |
| `POST` | `/admin/users/{id}/impersonate` | جعل هویت (با لاگ) |
| `GET/POST/PATCH` | `/admin/taxonomy/*` | مدیریت طبقه‌بندی |
| `GET/PATCH` | `/admin/point-rules` | قواعد امتیاز |
| `POST` | `/admin/point-rules/recalculate` | بازمحاسبهٔ گذشته‌نگر |
| `POST` | `/admin/point-entries/{id}/reverse` | اصلاح یک ردیف با رکورد معکوس (با دلیل) |
| `GET/POST/PATCH` | `/admin/badges` | مدیریت نشان |
| `GET/PATCH` | `/admin/settings` | تنظیمات |
| `GET` | `/admin/audit` | لاگ حسابرسی |
| `GET` | `/admin/outbox` | وضعیت صف ارسال با شمارش هر وضعیت — `message.outbox.view` |
| `POST` | `/admin/outbox/{id}/retry` | تلاش مجدد ارسال — `message.outbox.retry` |
| `POST` | `/admin/outbox/retry-dead` | همهٔ `DEAD`ها (یا یک کانال) به صف، پس از رفع قطعی |
| `GET` | `/admin/message-templates` | الگوهای پیام — `message.template.edit` |
| `PUT` | `/admin/message-templates/{code}/{channel}` | ساخت یا ویرایش الگو؛ متغیر ناشناخته ⇒ `TEMPLATE_INVALID` |
| `POST` | `/admin/message-templates/preview` | پیش‌نمایش با مقدارهای نمونه و تعداد بخش پیامک (FR-MSG-03) |
| `GET` | `/admin/health` | سلامت فنی |

---

## ۵.۱۳ فهرست کدهای خطا

| کد | HTTP | پیام فارسی |
|----|------|-----------|
| `OTP_RATE_LIMITED` | 429 | تعداد درخواست کد زیاد است. لطفاً بعداً تلاش کنید. |
| `OTP_INVALID` | 400 | کد واردشده نادرست است. |
| `OTP_EXPIRED` | 400 | مهلت کد تمام شده است. کد جدید بگیرید. |
| `TOKEN_REUSE_DETECTED` | 401 | نشست شما به‌دلایل امنیتی بسته شد. دوباره وارد شوید. |
| `ACCOUNT_LOCKED` | 423 | حساب شما موقتاً قفل شده است. |
| `PERMISSION_DENIED` | 403 | شما به این بخش دسترسی ندارید. |
| `PROFILE_INCOMPLETE` | 409 | برای این کار باید نیمرخ خود را تکمیل کنید. |
| `ALREADY_ENROLLED` | 409 | شما قبلاً در این درس ثبت‌نام کرده‌اید. |
| `OFFERING_FULL` | 409 | ظرفیت این درس تکمیل شده است. |
| `ENROLLMENT_CODE_INVALID` | 403 | کد ثبت‌نام نادرست است. |
| `QUIZ_NOT_OPEN` | 409 | این آزمون هنوز باز نشده است. |
| `QUIZ_CLOSED` | 409 | مهلت این آزمون به پایان رسیده است. |
| `ATTEMPTS_EXHAUSTED` | 409 | تعداد دفعات مجاز شرکت در آزمون تمام شده است. |
| `ATTEMPT_EXPIRED` | 409 | زمان آزمون شما به پایان رسیده است. |
| `ATTEMPT_ALREADY_SUBMITTED` | 409 | این آزمون قبلاً ارسال شده است. |
| `ACTIVE_ATTEMPT_EXISTS` | 409 | شما یک آزمون نیمه‌تمام دارید. |
| `APPEAL_WINDOW_CLOSED` | 409 | مهلت اعتراض به این نمره به پایان رسیده است. |
| `RESULT_NOT_AVAILABLE` | 409 | نتیجهٔ این آزمون هنوز منتشر نشده است. |
| `QUIZ_HAS_ATTEMPTS` | 409 | این آزمون تلاش ثبت‌شده دارد و سؤال‌هایش قابل تغییر نیست. |
| `QUIZ_HAS_NO_QUESTIONS` | 409 | آزمون بدون سؤال منتشر نمی‌شود. |
| `PROJECT_NOT_OPEN` | 409 | این پروژه پذیرش ندارد. |
| `PROJECT_CAPACITY_FULL` | 409 | ظرفیت این پروژه تکمیل شده است. |
| `DUPLICATE_APPLICATION` | 409 | شما قبلاً برای این پروژه درخواست داده‌اید. |
| `TOO_MANY_OPEN_APPLICATIONS` | 409 | حداکثر ۵ درخواست باز می‌توانید داشته باشید. |
| `NOT_TEAM_MEMBER` | 403 | شما عضو تیم این پروژه نیستید. |
| `MILESTONE_NOT_OPEN` | 409 | این مرحله پذیرای تحویل نیست. |
| `STAGE_CRITERIA_NOT_MET` | 409 | شرایط ارتقا به مرحلهٔ بعد فراهم نیست. |
| `TOPIC_ALREADY_RESERVED` | 409 | این موضوع رزرو شده است. |
| `FILE_TOO_LARGE` | 413 | حجم فایل بیش از حد مجاز است. |
| `CONTENT_TYPE_NOT_ALLOWED` | 415 | این نوع فایل مجاز نیست. |
| `FILE_SCAN_PENDING` | 409 | فایل در حال بررسی است. کمی صبر کنید. |
| `UPLOAD_INCOMPLETE` | 409 | آپلود این فایل کامل نشده است. |
| `CONCURRENT_MODIFICATION` | 409 | هم‌زمان کس دیگری همین را تغییر داد. دوباره تلاش کنید. |
| `DUPLICATE_VOTE` | 409 | شما قبلاً به این ایده رأی داده‌اید. |
| `VALIDATION_ERROR` | 422 | اطلاعات واردشده معتبر نیست. |
| `RATE_LIMITED` | 429 | درخواست‌های شما بیش از حد مجاز است. |
| `INTERNAL_ERROR` | 500 | خطایی رخ داد. کد پیگیری: {trace_id} |

---

## ۵.۱۴ الزامات پیاده‌سازی

- **بدون N+1:** هر endpoint فهرستی باید با تعداد ثابت کوئری اجرا شود.
  تست کارایی با شمارش کوئری (`pytest-sqlalchemy-queries`) الزامی است.
- **نسخهٔ OpenAPI** در CI با نسخهٔ قبلی مقایسه می‌شود؛ تغییر شکنندهٔ ناخواسته
  باعث شکست Build می‌شود.
- **تایپ‌های مشترک** با `openapi-typescript` تولید و در `packages/shared` کامیت می‌شوند.
- هر endpoint حداقل یک تست موفق و یک تست مجوز (۴۰۳) دارد.
