# ۰۴ — مدل داده

اسکیمای مرجع PostgreSQL 16. این سند مستقیماً به مهاجرت‌های Alembic ترجمه می‌شود.

---

## ۴.۰ قراردادهای عمومی

این قواعد بر **همهٔ** جداول اعمال می‌شوند:

| قاعده | جزئیات |
|-------|--------|
| کلید اصلی | `id UUID PRIMARY KEY DEFAULT uuidv7()` — تابع کمکی در مهاجرت اول تعریف می‌شود |
| نام جدول | جمع، snake_case انگلیسی (`course_offerings`) |
| زمان | `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`، `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` با تریگر |
| حذف نرم | `deleted_at TIMESTAMPTZ NULL` روی موجودیت‌های دامنه (D-15) |
| Enum | نوع `TEXT` + قید `CHECK`، نه `ENUM` بومی — افزودن مقدار جدید بدون قفل جدول |
| متن فارسی | `TEXT`، با ستون کمکی `*_normalized` برای جستجو در جداول پرجستجو |
| پول | `BIGINT` به **ریال**، هرگز `FLOAT` |
| درصد و امتیاز | `NUMERIC(6,2)` |
| JSON | `JSONB` با قید `CHECK (jsonb_typeof(col) = 'object')` |

### افزونه‌های لازم

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- رمزنگاری کد ملی، تولید تصادفی
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- جستجوی فارسی
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS citext;      -- ایمیل بدون حساسیت به بزرگی حروف
-- CREATE EXTENSION IF NOT EXISTS postgis;  -- فقط در صورت فعال‌سازی Smart City Lab
```

### تابع `uuidv7()`

PostgreSQL 16 این تابع را به‌صورت بومی ندارد (از نسخهٔ ۱۸ اضافه شده). پیاده‌سازی
زیر در مهاجرت ۰۰۱ تعریف می‌شود: ۴۸ بیت اول زمان میلی‌ثانیه‌ای یونیکس، بقیه تصادفی.
هنگام ارتقا به PG 18، این تابع حذف و تابع بومی جایگزین می‌شود (یک ADR لازم دارد).

```sql
CREATE OR REPLACE FUNCTION uuidv7() RETURNS uuid AS $$
DECLARE
  unix_ms  bigint := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;
  rand_a   bytea  := gen_random_bytes(10);
  ts_bytes bytea;
BEGIN
  ts_bytes := substring(int8send(unix_ms) FROM 3 FOR 6);   -- ۴۸ بیت زمان
  RETURN encode(
    ts_bytes
    -- نسخه ۷ در نیبل بالای بایت هفتم
    || set_byte(substring(rand_a FROM 1 FOR 2), 0,
                (get_byte(rand_a, 0) & 15) | 112)
    -- variant RFC 4122 در بایت نهم
    || set_byte(substring(rand_a FROM 3 FOR 8), 0,
                (get_byte(rand_a, 2) & 63) | 128),
    'hex')::uuid;
END;
$$ LANGUAGE plpgsql VOLATILE;
```

> **جایگزین:** اگر ترجیح می‌دهید شناسه در لایهٔ اپلیکیشن تولید شود، کتابخانهٔ
> `uuid6` در پایتون همین کار را می‌کند. تولید در دیتابیس انتخاب شده تا درج
> مستقیم SQL (مهاجرت، seed، اسکریپت) هم شناسهٔ درست بگیرد.

### تریگر به‌روزرسانی زمان

```sql
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$ LANGUAGE plpgsql;
-- به‌ازای هر جدول: CREATE TRIGGER trg_<t>_updated BEFORE UPDATE ON <t>
--                  FOR EACH ROW EXECUTE FUNCTION set_updated_at();
```

### تابع نرمال‌سازی متن فارسی

حیاتی برای جستجو. عربی/فارسی «ی» و «ک»، اعراب، و نیم‌فاصله را یکدست می‌کند.

```sql
CREATE OR REPLACE FUNCTION fa_normalize(input TEXT) RETURNS TEXT AS $$
  SELECT lower(trim(regexp_replace(
    translate(
      COALESCE(input, ''),
      'يكةأإآؤئىۀ' || U&'\0640',   -- عربی + کشیده
      'یکهاااییه'  || ''
    ),
    '[ً-ٰٟ‌‏]+', ' ', 'g'   -- اعراب، نیم‌فاصله، علائم جهت
  )));
$$ LANGUAGE sql IMMUTABLE STRICT;
```

> هر ستون قابل جستجو یک ستون تولیدشده دارد:
> `title_norm TEXT GENERATED ALWAYS AS (fa_normalize(title)) STORED`
> و روی آن `GIN (title_norm gin_trgm_ops)`.

---

## ۴.۱ نمودار موجودیت‌ها (سطح بالا)

```
                      ┌──────────┐
                      │  users   │
                      └────┬─────┘
          ┌────────────────┼────────────────┬──────────────┐
          │                │                │              │
   ┌──────┴─────┐   ┌──────┴──────┐  ┌──────┴──────┐ ┌─────┴──────┐
   │  profiles  │   │ user_roles  │  │point_entries│ │refresh_tok.│
   └──────┬─────┘   └─────────────┘  └─────────────┘ └────────────┘
          │
   ┌──────┴────────────┬──────────────────┐
   │                   │                  │
┌──┴──────────┐ ┌──────┴───────┐  ┌───────┴────────┐
│profile_skills│ │profile_assets│  │profile_interests│
└──────┬───────┘ └──────────────┘  └───────┬────────┘
       │                                    │
   ┌───┴────┐                          ┌────┴─────┐
   │ skills │                          │interests │
   └───┬────┘                          └────┬─────┘
       │                                    │
       │      ┌──────────────┐              │
       └──────┤   projects   ├──────────────┘
              └──────┬───────┘
     ┌───────────────┼───────────────┬──────────────┐
     │               │               │              │
┌────┴──────┐ ┌──────┴─────┐ ┌───────┴────┐ ┌───────┴────┐
│project_   │ │   teams    │ │ milestones │ │project_    │
│applications│ └──────┬─────┘ └──────┬─────┘ │required_*  │
└───────────┘        │              │       └────────────┘
                ┌────┴─────┐  ┌─────┴──────┐
                │team_     │  │deliverables│
                │members   │  └────────────┘
                └──────────┘

   ┌─────────┐    ┌──────────────────┐    ┌──────────────┐
   │ courses ├───►│course_offerings  ├───►│ course_weeks │
   └─────────┘    └────────┬─────────┘    └──────┬───────┘
                           │                     │
                  ┌────────┴──────┐     ┌────────┴────────┐
                  │  enrollments  │     │    resources    │
                  └───────────────┘     │     quizzes     │
                                        └────────┬────────┘
                                                 │
                                    ┌────────────┴─────────┐
                                    │  quiz_questions      │
                                    │  quiz_attempts       │
                                    │  quiz_answers        │
                                    └──────────────────────┘
```

---

## ۴.۲ هویت و دسترسی

### `users`

```sql
CREATE TABLE users (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  mobile            TEXT UNIQUE,                -- ^09\d{9}$ ذخیرهٔ نرمال‌شده
  email             CITEXT UNIQUE,
  username          TEXT UNIQUE,                -- برای /u/{username}
  password_hash     TEXT,                       -- argon2id، NULL اگر فقط OTP
  mobile_verified_at TIMESTAMPTZ,
  email_verified_at  TIMESTAMPTZ,
  status            TEXT NOT NULL DEFAULT 'ACTIVE'
                    CHECK (status IN ('ACTIVE','SUSPENDED','DEACTIVATED')),
  last_login_at     TIMESTAMPTZ,
  locale            TEXT NOT NULL DEFAULT 'fa',
  timezone          TEXT NOT NULL DEFAULT 'Asia/Tehran',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ,
  CONSTRAINT users_contact_required CHECK (mobile IS NOT NULL OR email IS NOT NULL)
);
CREATE INDEX idx_users_status ON users(status) WHERE deleted_at IS NULL;
```

### `roles` و `user_roles`

```sql
CREATE TABLE roles (
  code        TEXT PRIMARY KEY,   -- §06
  title_fa    TEXT NOT NULL,
  description TEXT,
  rank        INT NOT NULL        -- برای مقایسهٔ سطح دسترسی
);

CREATE TABLE user_roles (
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_code  TEXT NOT NULL REFERENCES roles(code),
  scope_type TEXT CHECK (scope_type IN ('GLOBAL','OFFERING','PROJECT','VENTURE')),
  scope_id   UUID,               -- NULL برای GLOBAL
  granted_by UUID REFERENCES users(id),
  granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, role_code, scope_type, COALESCE(scope_id, '00000000-0000-0000-0000-000000000000'::uuid))
);
CREATE INDEX idx_user_roles_scope ON user_roles(scope_type, scope_id);
```

> **نکتهٔ طراحی:** نقش می‌تواند **دامنه‌دار** باشد. مثلاً «مدیر پروژه» فقط برای
> یک پروژهٔ خاص. این از ساخت جداول عضویت موازی جلوگیری می‌کند.

### `refresh_tokens`

```sql
CREATE TABLE refresh_tokens (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   TEXT NOT NULL UNIQUE,      -- sha256
  family_id    UUID NOT NULL,             -- تشخیص سرقت توکن (FR-AUTH-03)
  parent_id    UUID REFERENCES refresh_tokens(id),
  user_agent   TEXT,
  ip_address   INET,
  expires_at   TIMESTAMPTZ NOT NULL,
  revoked_at   TIMESTAMPTZ,
  revoked_reason TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_refresh_user_active ON refresh_tokens(user_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_family ON refresh_tokens(family_id);
```

### `otp_challenges`

```sql
CREATE TABLE otp_challenges (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  channel     TEXT NOT NULL CHECK (channel IN ('SMS','EMAIL')),
  destination TEXT NOT NULL,             -- موبایل یا ایمیل، نرمال‌شده
  code_hash   TEXT NOT NULL,             -- bcrypt
  purpose     TEXT NOT NULL CHECK (purpose IN ('LOGIN','VERIFY_EMAIL','VERIFY_MOBILE','RESET_PASSWORD')),
  attempts    INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  consumed_at TIMESTAMPTZ,
  expires_at  TIMESTAMPTZ NOT NULL,
  ip_address  INET,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_otp_dest_active ON otp_challenges(destination, purpose)
  WHERE consumed_at IS NULL;
```

---

## ۴.۳ نیمرخ و ارزیابی

### `profiles`

```sql
CREATE TABLE profiles (
  user_id            UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  first_name         TEXT NOT NULL,
  last_name          TEXT NOT NULL,
  display_name       TEXT,
  national_id_enc    BYTEA,              -- pgcrypto، §11
  national_id_hash   TEXT UNIQUE,        -- برای بررسی یکتایی بدون رمزگشایی
  birth_year         INT CHECK (birth_year BETWEEN 1300 AND 1420),  -- شمسی
  gender             TEXT CHECK (gender IN ('M','F','UNDISCLOSED')),
  avatar_key         TEXT,               -- کلید S3
  bio                TEXT CHECK (length(bio) <= 500),

  -- اطلاعات دانشگاهی
  university_id      UUID REFERENCES universities(id),
  field_of_study     TEXT,
  degree_level       TEXT CHECK (degree_level IN ('ASSOCIATE','BACHELOR','MASTER','PHD','OTHER')),
  student_number     TEXT,
  entry_year         INT,

  -- ترجیحات کاری (گام ۴ ارزیابی)
  work_style         TEXT CHECK (work_style IN ('SOLO','TEAM','EITHER')),
  primary_goal       TEXT CHECK (primary_goal IN
                       ('GRADE','LEARNING','PUBLICATION','INCOME','STARTUP','EMPLOYMENT')),
  weekly_hours       INT CHECK (weekly_hours BETWEEN 0 AND 80),

  -- حریم خصوصی
  is_public          BOOLEAN NOT NULL DEFAULT false,
  privacy_settings   JSONB NOT NULL DEFAULT '{}'::jsonb,
  show_in_leaderboard BOOLEAN NOT NULL DEFAULT true,

  survey_completed_steps INT NOT NULL DEFAULT 0 CHECK (survey_completed_steps BETWEEN 0 AND 4),
  survey_updated_at  TIMESTAMPTZ,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_profiles_public ON profiles(is_public) WHERE is_public;
CREATE INDEX idx_profiles_university ON profiles(university_id);
```

### طبقه‌بندی‌ها: `skills`, `assets`, `interests`

```sql
CREATE TABLE skills (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  code       TEXT NOT NULL UNIQUE,      -- 'PYTHON', 'SUMO', ...
  title_fa   TEXT NOT NULL,
  title_en   TEXT NOT NULL,
  category   TEXT NOT NULL CHECK (category IN ('SOFTWARE','ANALYSIS','DOMAIN','SOFT','LANGUAGE')),
  icon       TEXT,
  sort_order INT NOT NULL DEFAULT 0,
  is_core    BOOLEAN NOT NULL DEFAULT false,  -- در گام ۱ نیمرخ پیش‌فرض نمایش داده می‌شود
  is_active  BOOLEAN NOT NULL DEFAULT true
);
-- حداکثر ۱۰ مهارت می‌تواند is_core باشد؛ بقیه پشت «مهارت‌های بیشتر» پنهان‌اند.
-- این قید در لایهٔ سرویس و در تست داده‌های اولیه بررسی می‌شود.

CREATE TABLE assets (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  code       TEXT NOT NULL UNIQUE,      -- 'CAR','PICKUP','MOTORCYCLE','CAMERA',...
  title_fa   TEXT NOT NULL,
  category   TEXT NOT NULL CHECK (category IN ('COMPUTING','VEHICLE','EQUIPMENT','CONNECTIVITY','SPACE')),
  icon       TEXT,
  sort_order INT NOT NULL DEFAULT 0,
  is_active  BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE interests (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  code       TEXT NOT NULL UNIQUE,      -- 'RESEARCH','PROGRAMMING','MARKETING',...
  title_fa   TEXT NOT NULL,
  icon       TEXT,
  sort_order INT NOT NULL DEFAULT 0,
  is_active  BOOLEAN NOT NULL DEFAULT true
);
```

### پاسخ‌های نیمرخ

```sql
CREATE TABLE profile_skills (
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  skill_id     UUID NOT NULL REFERENCES skills(id),
  level        INT NOT NULL CHECK (level BETWEEN 1 AND 5),
  verified_by  UUID REFERENCES users(id),           -- FR-PROF-04
  verified_at  TIMESTAMPTZ,
  evidence_type TEXT CHECK (evidence_type IN ('DELIVERABLE','QUIZ','MANUAL')),
  evidence_id  UUID,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, skill_id)
);
CREATE INDEX idx_profile_skills_lookup ON profile_skills(skill_id, level DESC);

CREATE TABLE profile_assets (
  user_id  UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  asset_id UUID NOT NULL REFERENCES assets(id),
  note     TEXT,
  PRIMARY KEY (user_id, asset_id)
);
CREATE INDEX idx_profile_assets_lookup ON profile_assets(asset_id);

CREATE TABLE profile_interests (
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  interest_id UUID NOT NULL REFERENCES interests(id),
  level       INT NOT NULL CHECK (level BETWEEN 1 AND 5),
  PRIMARY KEY (user_id, interest_id)
);
CREATE INDEX idx_profile_interests_lookup ON profile_interests(interest_id, level DESC);
```

### تاریخچهٔ نسخه‌های ارزیابی

```sql
CREATE TABLE profile_survey_versions (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  snapshot   JSONB NOT NULL,     -- کل وضعیت skills/assets/interests/prefs
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_survey_versions_user ON profile_survey_versions(user_id, created_at DESC);
```

> **چرا تاریخچه؟** تحلیل رشد مهارت دانشجو در طول تحصیل، یک خروجی پژوهشی ارزشمند است.

### `universities`

```sql
CREATE TABLE universities (
  id        UUID PRIMARY KEY DEFAULT uuidv7(),
  title_fa  TEXT NOT NULL,
  title_en  TEXT,
  city      TEXT,
  province  TEXT,
  type      TEXT CHECK (type IN ('STATE','AZAD','PAYAMNOOR','NONPROFIT','APPLIED','OTHER')),
  is_active BOOLEAN NOT NULL DEFAULT true
);
```

---

## ۴.۴ آموزش

### `terms`, `courses`, `course_offerings`

```sql
CREATE TABLE terms (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  code       TEXT NOT NULL UNIQUE,      -- '1404-2'
  title_fa   TEXT NOT NULL,             -- 'نیم‌سال دوم ۱۴۰۴-۱۴۰۵'
  starts_on  DATE NOT NULL,
  ends_on    DATE NOT NULL,
  is_current BOOLEAN NOT NULL DEFAULT false,
  CONSTRAINT terms_date_order CHECK (ends_on > starts_on)
);
CREATE UNIQUE INDEX idx_terms_single_current ON terms(is_current) WHERE is_current;

CREATE TABLE courses (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  code         TEXT NOT NULL UNIQUE,     -- 'TRANSPORT-PLAN'
  slug         TEXT NOT NULL UNIQUE,
  title_fa     TEXT NOT NULL,
  title_en     TEXT,
  description  TEXT,
  degree_level TEXT CHECK (degree_level IN ('BACHELOR','MASTER','PHD','PUBLIC')),
  credits      INT,
  cover_key    TEXT,
  is_public    BOOLEAN NOT NULL DEFAULT false,  -- قابل ثبت‌نام برای PUBLIC_LEARNER
  is_active    BOOLEAN NOT NULL DEFAULT true,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ,
  title_norm   TEXT GENERATED ALWAYS AS (fa_normalize(title_fa)) STORED
);
CREATE INDEX idx_courses_search ON courses USING GIN (title_norm gin_trgm_ops);

CREATE TABLE course_offerings (
  id                UUID PRIMARY KEY DEFAULT uuidv7(),
  course_id         UUID NOT NULL REFERENCES courses(id),
  term_id           UUID NOT NULL REFERENCES terms(id),
  instructor_id     UUID NOT NULL REFERENCES users(id),
  capacity          INT CHECK (capacity > 0),
  enrollment_code   TEXT,
  requires_approval BOOLEAN NOT NULL DEFAULT false,
  status            TEXT NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT','OPEN','IN_PROGRESS','CLOSED','ARCHIVED')),
  grading_policy    JSONB NOT NULL DEFAULT '{}'::jsonb,  -- وزن آزمون/پروژه/حضور
  syllabus_key      TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at        TIMESTAMPTZ,
  UNIQUE (course_id, term_id, instructor_id)
);
CREATE INDEX idx_offerings_instructor ON course_offerings(instructor_id, status);
CREATE INDEX idx_offerings_term ON course_offerings(term_id, status);
```

**ساختار `grading_policy`:**
```json
{ "quiz": 30, "project": 50, "attendance": 10, "participation": 10 }
```
مجموع باید ۱۰۰ باشد — با قید در لایهٔ اپلیکیشن بررسی می‌شود.

### `enrollments`

```sql
CREATE TABLE enrollments (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  offering_id  UUID NOT NULL REFERENCES course_offerings(id),
  student_id   UUID NOT NULL REFERENCES users(id),
  status       TEXT NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING','ACTIVE','DROPPED','COMPLETED','REJECTED')),
  final_grade  NUMERIC(5,2) CHECK (final_grade BETWEEN 0 AND 20),
  enrolled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  decided_at   TIMESTAMPTZ,
  decided_by   UUID REFERENCES users(id),
  UNIQUE (offering_id, student_id)
);
CREATE INDEX idx_enrollments_student ON enrollments(student_id, status);
CREATE INDEX idx_enrollments_offering ON enrollments(offering_id, status);
```

### `course_weeks` و `resources`

```sql
CREATE TABLE course_weeks (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  offering_id  UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
  week_number  INT NOT NULL CHECK (week_number BETWEEN 1 AND 17),
  title_fa     TEXT NOT NULL,
  description  TEXT,
  objectives   TEXT[],                -- اهداف یادگیری
  status       TEXT NOT NULL DEFAULT 'DRAFT'
               CHECK (status IN ('DRAFT','PUBLISHED','ARCHIVED')),
  publish_at   TIMESTAMPTZ,           -- انتشار زمان‌بندی‌شده
  published_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (offering_id, week_number)
);
CREATE INDEX idx_weeks_publish_queue ON course_weeks(publish_at)
  WHERE status = 'DRAFT' AND publish_at IS NOT NULL;

CREATE TABLE resources (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  week_id      UUID NOT NULL REFERENCES course_weeks(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN ('PDF','VIDEO','LINK','SLIDE','DATASET','CODE','OTHER')),
  title_fa     TEXT NOT NULL,
  description  TEXT,
  file_id      UUID REFERENCES files(id),
  external_url TEXT,
  duration_sec INT,                   -- برای ویدئو
  is_downloadable BOOLEAN NOT NULL DEFAULT true,
  is_required  BOOLEAN NOT NULL DEFAULT true,
  sort_order   INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT resources_source_required CHECK (file_id IS NOT NULL OR external_url IS NOT NULL)
);
CREATE INDEX idx_resources_week ON resources(week_id, sort_order);

CREATE TABLE resource_progress (
  user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resource_id  UUID NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
  status       TEXT NOT NULL DEFAULT 'NOT_STARTED'
               CHECK (status IN ('NOT_STARTED','IN_PROGRESS','COMPLETED')),
  position_sec INT,                   -- ادامه از محل قطع ویدئو
  percent      NUMERIC(5,2) DEFAULT 0,
  first_opened_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, resource_id)
);
```

### `attendance` و `announcements`

```sql
CREATE TABLE class_sessions (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  offering_id UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
  week_number INT,
  held_on     DATE NOT NULL,
  topic       TEXT,
  UNIQUE (offering_id, held_on)
);

CREATE TABLE attendance_records (
  session_id UUID NOT NULL REFERENCES class_sessions(id) ON DELETE CASCADE,
  student_id UUID NOT NULL REFERENCES users(id),
  status     TEXT NOT NULL CHECK (status IN ('PRESENT','ABSENT','LATE','EXCUSED')),
  note       TEXT,
  recorded_by UUID REFERENCES users(id),
  recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (session_id, student_id)
);

CREATE TABLE announcements (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  offering_id UUID REFERENCES course_offerings(id) ON DELETE CASCADE,
  project_id  UUID REFERENCES projects(id) ON DELETE CASCADE,
  author_id   UUID NOT NULL REFERENCES users(id),
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  priority    TEXT NOT NULL DEFAULT 'NORMAL'
              CHECK (priority IN ('NORMAL','IMPORTANT','URGENT')),
  published_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at  TIMESTAMPTZ,
  CONSTRAINT announcements_target CHECK (
    (offering_id IS NOT NULL)::int + (project_id IS NOT NULL)::int = 1)
);
```

---

## ۴.۵ آزمون

### `quizzes` و بانک سؤال

```sql
CREATE TABLE quizzes (
  id              UUID PRIMARY KEY DEFAULT uuidv7(),
  offering_id     UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
  week_id         UUID REFERENCES course_weeks(id) ON DELETE SET NULL,
  title_fa        TEXT NOT NULL,
  description     TEXT,
  duration_min    INT NOT NULL CHECK (duration_min BETWEEN 1 AND 300),
  opens_at        TIMESTAMPTZ NOT NULL,
  closes_at       TIMESTAMPTZ NOT NULL,
  max_attempts    INT NOT NULL DEFAULT 1 CHECK (max_attempts BETWEEN 1 AND 10),
  passing_score   NUMERIC(5,2),
  shuffle_questions BOOLEAN NOT NULL DEFAULT true,
  shuffle_options   BOOLEAN NOT NULL DEFAULT true,
  result_visibility TEXT NOT NULL DEFAULT 'AFTER_CLOSE'
                    CHECK (result_visibility IN ('IMMEDIATE','AFTER_CLOSE','MANUAL')),
  show_correct_answers BOOLEAN NOT NULL DEFAULT true,
  status          TEXT NOT NULL DEFAULT 'DRAFT'
                  CHECK (status IN ('DRAFT','PUBLISHED','CLOSED')),
  total_points    NUMERIC(6,2) NOT NULL DEFAULT 0,  -- مشتق، با تریگر به‌روز می‌شود
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT quizzes_window CHECK (closes_at > opens_at)
);
CREATE INDEX idx_quizzes_offering ON quizzes(offering_id, status);

CREATE TABLE question_bank (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_id     UUID NOT NULL REFERENCES users(id),
  course_id    UUID REFERENCES courses(id),
  category     TEXT,
  difficulty   INT CHECK (difficulty BETWEEN 1 AND 5),
  kind         TEXT NOT NULL CHECK (kind IN
               ('SINGLE_CHOICE','MULTI_CHOICE','TRUE_FALSE','SHORT_ANSWER','NUMERIC','ESSAY','MATCHING')),
  body         TEXT NOT NULL,
  payload      JSONB NOT NULL,      -- گزینه‌ها/پاسخ‌ها، ساختار بر اساس kind
  explanation  TEXT,
  usage_count  INT NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at   TIMESTAMPTZ
);

CREATE TABLE quiz_questions (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  quiz_id     UUID NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
  bank_id     UUID REFERENCES question_bank(id),   -- منشأ، اگر از بانک آمده
  kind        TEXT NOT NULL CHECK (kind IN
              ('SINGLE_CHOICE','MULTI_CHOICE','TRUE_FALSE','SHORT_ANSWER','NUMERIC','ESSAY','MATCHING')),
  body        TEXT NOT NULL,
  payload     JSONB NOT NULL,
  explanation TEXT,
  points      NUMERIC(5,2) NOT NULL DEFAULT 1 CHECK (points > 0),
  sort_order  INT NOT NULL DEFAULT 0
);
CREATE INDEX idx_quiz_questions_quiz ON quiz_questions(quiz_id, sort_order);
```

**ساختار `payload` بر اساس نوع سؤال:**

```jsonc
// SINGLE_CHOICE / MULTI_CHOICE
{ "options": [{"id":"a","text":"گزینه ۱"}, …], "correct": ["a"] }

// TRUE_FALSE
{ "correct": true }

// SHORT_ANSWER
{ "accepted": ["پاسخ ۱","پاسخ دوم"], "case_sensitive": false }

// NUMERIC
{ "correct": 12.5, "tolerance": 0.05, "unit": "km/h" }

// MATCHING
{ "left": [{"id":"l1","text":"…"}], "right": [{"id":"r1","text":"…"}],
  "correct": [["l1","r1"]] }

// ESSAY
{ "min_words": 50, "max_words": 500, "rubric": "…" }
```

### `quiz_attempts` و `quiz_answers`

```sql
CREATE TABLE quiz_attempts (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  quiz_id       UUID NOT NULL REFERENCES quizzes(id),
  student_id    UUID NOT NULL REFERENCES users(id),
  attempt_no    INT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'IN_PROGRESS'
                CHECK (status IN ('IN_PROGRESS','SUBMITTED','AUTO_SUBMITTED','GRADED','VOIDED')),
  question_order UUID[],          -- ترتیب قطعی سؤالات این تلاش
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at    TIMESTAMPTZ NOT NULL,       -- started_at + duration، مرجع سرور
  submitted_at  TIMESTAMPTZ,
  graded_at     TIMESTAMPTZ,
  auto_score    NUMERIC(6,2),
  manual_score  NUMERIC(6,2),
  total_score   NUMERIC(6,2),
  is_provisional BOOLEAN NOT NULL DEFAULT false,   -- منتظر تصحیح تشریحی
  integrity_events JSONB NOT NULL DEFAULT '[]'::jsonb,
  UNIQUE (quiz_id, student_id, attempt_no)
);
CREATE UNIQUE INDEX idx_one_active_attempt ON quiz_attempts(quiz_id, student_id)
  WHERE status = 'IN_PROGRESS';
CREATE INDEX idx_attempts_grading ON quiz_attempts(quiz_id)
  WHERE status = 'SUBMITTED' OR status = 'AUTO_SUBMITTED';

CREATE TABLE quiz_answers (
  attempt_id   UUID NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
  question_id  UUID NOT NULL REFERENCES quiz_questions(id),
  response     JSONB,                -- ساختار متناظر با kind
  is_flagged   BOOLEAN NOT NULL DEFAULT false,   -- دانشجو برای مرور نشان کرده
  auto_score   NUMERIC(5,2),
  manual_score NUMERIC(5,2),
  grader_id    UUID REFERENCES users(id),
  feedback     TEXT,
  answered_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (attempt_id, question_id)
);

CREATE TABLE grade_appeals (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  attempt_id  UUID NOT NULL REFERENCES quiz_attempts(id),
  question_id UUID REFERENCES quiz_questions(id),
  student_id  UUID NOT NULL REFERENCES users(id),
  reason      TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'OPEN'
              CHECK (status IN ('OPEN','ACCEPTED','REJECTED')),
  response    TEXT,
  resolved_by UUID REFERENCES users(id),
  resolved_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## ۴.۶ پروژه — هستهٔ سامانه

### `projects`

```sql
CREATE TABLE projects (
  id             UUID PRIMARY KEY DEFAULT uuidv7(),
  slug           TEXT NOT NULL UNIQUE,
  title_fa       TEXT NOT NULL,
  summary        TEXT NOT NULL CHECK (length(summary) <= 280),
  description    TEXT NOT NULL,
  kind           TEXT NOT NULL CHECK (kind IN ('A_VENTURE','B_RESEARCH','C_PROBLEM','D_PERSONAL')),
  status         TEXT NOT NULL DEFAULT 'DRAFT'
                 CHECK (status IN ('DRAFT','OPEN','IN_PROGRESS','PAUSED','COMPLETED','CANCELLED')),
  lead_id        UUID NOT NULL REFERENCES users(id),
  offering_id    UUID REFERENCES course_offerings(id),    -- اگر به درسی متصل است
  venture_id     UUID REFERENCES ventures(id),
  origin_idea_id UUID REFERENCES ideas(id),               -- FR-IDEA-03

  -- مشخصات تطابق (§08)
  time_commitment_hpw INT CHECK (time_commitment_hpw BETWEEN 1 AND 60),
  team_size_min  INT NOT NULL DEFAULT 1 CHECK (team_size_min >= 1),
  team_size_max  INT NOT NULL DEFAULT 1,
  work_style     TEXT NOT NULL DEFAULT 'EITHER' CHECK (work_style IN ('SOLO','TEAM','EITHER')),
  difficulty     INT NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),

  expected_output TEXT NOT NULL,      -- «در پایان چه تحویل می‌شود؟»
  rewards        JSONB NOT NULL DEFAULT '{}'::jsonb,
  cover_key      TEXT,
  tags           TEXT[] NOT NULL DEFAULT '{}',

  starts_on      DATE,
  deadline_on    DATE,
  applications_close_at TIMESTAMPTZ,

  health         TEXT NOT NULL DEFAULT 'HEALTHY'
                 CHECK (health IN ('HEALTHY','AT_RISK','STALLED')),
  last_activity_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at     TIMESTAMPTZ,

  search_norm    TEXT GENERATED ALWAYS AS
                 (fa_normalize(title_fa || ' ' || summary)) STORED,
  CONSTRAINT projects_team_size CHECK (team_size_max >= team_size_min)
);
CREATE INDEX idx_projects_search ON projects USING GIN (search_norm gin_trgm_ops);
CREATE INDEX idx_projects_open ON projects(kind, status) WHERE status = 'OPEN' AND deleted_at IS NULL;
CREATE INDEX idx_projects_tags ON projects USING GIN (tags);
CREATE INDEX idx_projects_health ON projects(health) WHERE health <> 'HEALTHY';
```

**ساختار `rewards`:**
```json
{ "points": 250, "grade_weight": 20, "revenue_share_percent": 15, "certificate": true }
```

### نیازمندی‌های پروژه

```sql
CREATE TABLE project_required_skills (
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  skill_id   UUID NOT NULL REFERENCES skills(id),
  min_level  INT NOT NULL CHECK (min_level BETWEEN 1 AND 5),
  weight     INT NOT NULL DEFAULT 1 CHECK (weight BETWEEN 1 AND 3),
  is_teachable BOOLEAN NOT NULL DEFAULT false,   -- «اگر بلد نیستی، یاد می‌گیری»
  PRIMARY KEY (project_id, skill_id)
);

CREATE TABLE project_required_assets (
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  asset_id    UUID NOT NULL REFERENCES assets(id),
  is_mandatory BOOLEAN NOT NULL DEFAULT false,
  PRIMARY KEY (project_id, asset_id)
);

CREATE TABLE project_interests (
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  interest_id UUID NOT NULL REFERENCES interests(id),
  PRIMARY KEY (project_id, interest_id)
);

CREATE TABLE project_roles (          -- FR-VEN-02: نقش‌های کاری داخل پروژه
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title_fa    TEXT NOT NULL,          -- 'بازاریاب'، 'تولیدکنندهٔ محتوا'
  description TEXT,
  slots       INT NOT NULL DEFAULT 1,
  filled      INT NOT NULL DEFAULT 0
);
```

### تیم و عضویت

```sql
CREATE TABLE teams (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  venture_id UUID REFERENCES ventures(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT teams_owner CHECK (
    (project_id IS NOT NULL)::int + (venture_id IS NOT NULL)::int = 1)
);

CREATE TABLE team_members (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  team_id    UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id),
  role_id    UUID REFERENCES project_roles(id),
  is_lead    BOOLEAN NOT NULL DEFAULT false,
  status     TEXT NOT NULL DEFAULT 'ACTIVE'
             CHECK (status IN ('ACTIVE','LEFT','REMOVED')),
  joined_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  left_at    TIMESTAMPTZ,
  leave_reason TEXT
);
CREATE UNIQUE INDEX idx_team_member_active ON team_members(team_id, user_id)
  WHERE status = 'ACTIVE';
CREATE INDEX idx_team_members_user ON team_members(user_id, status);
```

### درخواست پیوستن

```sql
CREATE TABLE project_applications (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  applicant_id UUID NOT NULL REFERENCES users(id),
  role_id      UUID REFERENCES project_roles(id),
  motivation   TEXT NOT NULL CHECK (length(motivation) <= 500),
  match_score  NUMERIC(5,2),          -- عکس‌برداری از امتیاز تطابق در لحظهٔ ارسال
  match_breakdown JSONB,              -- برای نمایش به مدیر پروژه
  status       TEXT NOT NULL DEFAULT 'PENDING'
               CHECK (status IN ('PENDING','ACCEPTED','REJECTED','WAITLISTED','WITHDRAWN')),
  decision_note TEXT,
  decided_by   UUID REFERENCES users(id),
  decided_at   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (project_id, applicant_id)
);
CREATE INDEX idx_applications_pending ON project_applications(project_id)
  WHERE status = 'PENDING';
CREATE INDEX idx_applications_user ON project_applications(applicant_id, status);
```

### مراحل و تحویل‌دادنی

```sql
CREATE TABLE milestones (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  title_fa    TEXT NOT NULL,
  description TEXT,
  sort_order  INT NOT NULL DEFAULT 0,
  due_on      DATE,
  points      NUMERIC(6,2) NOT NULL DEFAULT 0,
  is_required BOOLEAN NOT NULL DEFAULT true,
  output_kind TEXT CHECK (output_kind IN ('DOCUMENT','CODE','DATA','MEDIA','SALES','MIXED')),
  checklist   JSONB NOT NULL DEFAULT '[]'::jsonb,   -- معیارهای کیفیت
  status      TEXT NOT NULL DEFAULT 'PENDING'
              CHECK (status IN ('PENDING','IN_PROGRESS','SUBMITTED','APPROVED','OVERDUE')),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_milestones_project ON milestones(project_id, sort_order);
CREATE INDEX idx_milestones_due ON milestones(due_on)
  WHERE status IN ('PENDING','IN_PROGRESS');

CREATE TABLE deliverables (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  milestone_id UUID NOT NULL REFERENCES milestones(id) ON DELETE CASCADE,
  submitter_id UUID NOT NULL REFERENCES users(id),
  version      INT NOT NULL DEFAULT 1,
  body         TEXT,
  links        TEXT[] NOT NULL DEFAULT '{}',
  status       TEXT NOT NULL DEFAULT 'SUBMITTED'
               CHECK (status IN ('SUBMITTED','UNDER_REVIEW','APPROVED','CHANGES_REQUESTED','REJECTED')),
  score        NUMERIC(6,2),
  feedback     TEXT,
  rubric_scores JSONB,
  reviewed_by  UUID REFERENCES users(id),
  reviewed_at  TIMESTAMPTZ,
  submitted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (milestone_id, submitter_id, version)
);
CREATE INDEX idx_deliverables_review_queue ON deliverables(status, submitted_at)
  WHERE status IN ('SUBMITTED','UNDER_REVIEW');

CREATE TABLE deliverable_files (
  deliverable_id UUID NOT NULL REFERENCES deliverables(id) ON DELETE CASCADE,
  file_id        UUID NOT NULL REFERENCES files(id),
  PRIMARY KEY (deliverable_id, file_id)
);
```

### تخته وظایف و بازتاب

```sql
CREATE TABLE project_tasks (
  id           UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id   UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  milestone_id UUID REFERENCES milestones(id) ON DELETE SET NULL,
  title        TEXT NOT NULL,
  description  TEXT,
  assignee_id  UUID REFERENCES users(id),
  status       TEXT NOT NULL DEFAULT 'TODO' CHECK (status IN ('TODO','DOING','DONE')),
  due_on       DATE,
  sort_order   INT NOT NULL DEFAULT 0,
  created_by   UUID NOT NULL REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_tasks_project_status ON project_tasks(project_id, status, sort_order);

CREATE TABLE project_messages (        -- FR-PRJ-06: گفتگوی تیمی
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  parent_id  UUID REFERENCES project_messages(id),   -- نخ یک‌سطحی
  author_id  UUID NOT NULL REFERENCES users(id),
  body       TEXT NOT NULL,
  file_id    UUID REFERENCES files(id),
  edited_at  TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);
CREATE INDEX idx_project_messages ON project_messages(project_id, created_at DESC)
  WHERE deleted_at IS NULL;
-- نخ فقط یک سطح عمق دارد: پاسخ به پاسخ ممنوع
-- (در لایهٔ سرویس بررسی می‌شود: parent.parent_id باید NULL باشد)

CREATE TABLE project_activities (      -- FR-PRJ-06: جریان فعالیت
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  actor_id    UUID REFERENCES users(id),
  kind        TEXT NOT NULL,          -- 'MEMBER_JOINED','DELIVERABLE_SUBMITTED',…
  summary     TEXT NOT NULL,          -- متن فارسی آمادهٔ نمایش
  entity_type TEXT,
  entity_id   UUID,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_project_activities ON project_activities(project_id, created_at DESC);

CREATE TABLE project_reflections (
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id),
  learned    TEXT NOT NULL,
  challenges TEXT,
  would_do_differently TEXT,
  satisfaction INT CHECK (satisfaction BETWEEN 1 AND 5),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, user_id)
);

CREATE TABLE peer_evaluations (
  project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  evaluator_id UUID NOT NULL REFERENCES users(id),
  evaluatee_id UUID NOT NULL REFERENCES users(id),
  contribution INT NOT NULL CHECK (contribution BETWEEN 1 AND 5),
  reliability  INT CHECK (reliability BETWEEN 1 AND 5),
  note         TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (project_id, evaluator_id, evaluatee_id),
  CONSTRAINT peer_no_self CHECK (evaluator_id <> evaluatee_id)
);

CREATE TABLE certificates (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  public_code TEXT NOT NULL UNIQUE,        -- کد کوتاه برای /verify/{code}
  user_id     UUID NOT NULL REFERENCES users(id),
  kind        TEXT NOT NULL CHECK (kind IN ('PROJECT','COURSE','RESEARCH_LEVEL')),
  subject_id  UUID NOT NULL,
  title_fa    TEXT NOT NULL,
  issued_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  issued_by   UUID REFERENCES users(id),
  metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
  revoked_at  TIMESTAMPTZ
);
```

---

## ۴.۷ کارآفرینی، پژوهش، ایده

```sql
CREATE TABLE ventures (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  slug          TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL,
  pitch         TEXT NOT NULL CHECK (length(pitch) <= 280),
  description   TEXT,
  problem       TEXT,
  target_market TEXT,
  revenue_model TEXT,
  stage         TEXT NOT NULL DEFAULT 'IDEA'
                CHECK (stage IN ('IDEA','VALIDATION','MVP','FIRST_REVENUE','GROWTH','PAUSED','CLOSED')),
  founder_id    UUID NOT NULL REFERENCES users(id),
  looking_for_cofounder BOOLEAN NOT NULL DEFAULT false,
  needed_roles  TEXT[],
  logo_key      TEXT,
  origin_idea_id UUID REFERENCES ideas(id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ
);

CREATE TABLE venture_metrics (          -- FR-VEN-02/03
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  venture_id UUID REFERENCES ventures(id) ON DELETE CASCADE,
  project_id UUID,   -- کلید خارجی در مهاجرت ۰۱۰ افزوده می‌شود (ترتیب وابستگی)
  user_id    UUID NOT NULL REFERENCES users(id),
  metric     TEXT NOT NULL CHECK (metric IN
             ('CALLS','MEETINGS','LEADS','SALES_COUNT','SALES_AMOUNT','CONTENT_PIECES','CUSTOMERS')),
  value      BIGINT NOT NULL,          -- مبلغ به ریال برای SALES_AMOUNT
  occurred_on DATE NOT NULL,
  note       TEXT,
  evidence_file_id UUID REFERENCES files(id),
  verified_by UUID REFERENCES users(id),
  verified_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_venture_metrics_lookup ON venture_metrics(venture_id, metric, occurred_on);
CREATE INDEX idx_venture_metrics_user ON venture_metrics(user_id, occurred_on DESC);

CREATE TABLE research_tracks (
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  level       INT NOT NULL CHECK (level BETWEEN 1 AND 4),
  status      TEXT NOT NULL DEFAULT 'IN_PROGRESS'
              CHECK (status IN ('IN_PROGRESS','SUBMITTED','APPROVED')),
  mentor_id   UUID REFERENCES users(id),
  deliverable_id UUID REFERENCES deliverables(id),
  started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  approved_at TIMESTAMPTZ,
  PRIMARY KEY (user_id, level)
);

CREATE TABLE research_outputs (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  owner_id   UUID NOT NULL REFERENCES users(id),
  kind       TEXT NOT NULL CHECK (kind IN ('JOURNAL','CONFERENCE','THESIS','REPORT','PREPRINT')),
  title      TEXT NOT NULL,
  authors    TEXT NOT NULL,
  venue      TEXT,
  quartile   TEXT CHECK (quartile IN ('Q1','Q2','Q3','Q4','NA')),
  status     TEXT NOT NULL DEFAULT 'DRAFT'
             CHECK (status IN ('DRAFT','SUBMITTED','UNDER_REVIEW','REVISION','ACCEPTED','PUBLISHED','REJECTED')),
  doi        TEXT,
  url        TEXT,
  file_id    UUID REFERENCES files(id),
  project_id UUID REFERENCES projects(id),
  submitted_on DATE,
  published_on DATE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE research_topics (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  proposer_id UUID NOT NULL REFERENCES users(id),
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  prerequisites TEXT,
  level       INT CHECK (level BETWEEN 1 AND 4),
  status      TEXT NOT NULL DEFAULT 'OPEN'
              CHECK (status IN ('OPEN','RESERVED','TAKEN','CLOSED')),
  reserved_by UUID REFERENCES users(id),
  reserved_at TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_topics_reservation_expiry ON research_topics(reserved_at)
  WHERE status = 'RESERVED';

CREATE TABLE ideas (
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  author_id   UUID NOT NULL REFERENCES users(id),
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  problem     TEXT,
  category    TEXT,
  tags        TEXT[] NOT NULL DEFAULT '{}',
  is_anonymous BOOLEAN NOT NULL DEFAULT false,
  status      TEXT NOT NULL DEFAULT 'OPEN'
              CHECK (status IN ('OPEN','PROMOTED','ARCHIVED')),
  vote_count  INT NOT NULL DEFAULT 0,       -- غیرنرمال، با تریگر نگهداری می‌شود
  comment_count INT NOT NULL DEFAULT 0,
  promoted_to_type TEXT CHECK (promoted_to_type IN ('PROJECT','VENTURE')),
  promoted_to_id UUID,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at  TIMESTAMPTZ,
  search_norm TEXT GENERATED ALWAYS AS (fa_normalize(title || ' ' || body)) STORED
);
CREATE INDEX idx_ideas_search ON ideas USING GIN (search_norm gin_trgm_ops);
CREATE INDEX idx_ideas_ranking ON ideas(vote_count DESC, created_at DESC) WHERE status = 'OPEN';

CREATE TABLE idea_votes (
  idea_id    UUID NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (idea_id, user_id)
);

CREATE TABLE idea_comments (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  idea_id    UUID NOT NULL REFERENCES ideas(id) ON DELETE CASCADE,
  author_id  UUID NOT NULL REFERENCES users(id),
  body       TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at TIMESTAMPTZ
);

CREATE TABLE team_openings (           -- FR-TEAM-02
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  poster_id   UUID NOT NULL REFERENCES users(id),
  project_id  UUID REFERENCES projects(id) ON DELETE CASCADE,
  venture_id  UUID REFERENCES ventures(id) ON DELETE CASCADE,
  idea_id     UUID REFERENCES ideas(id) ON DELETE CASCADE,
  title       TEXT NOT NULL,
  description TEXT NOT NULL,
  needed_skills UUID[] NOT NULL DEFAULT '{}',
  commitment_hpw INT,
  status      TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','FILLED','EXPIRED')),
  expires_at  TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '30 days'),
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

---

## ۴.۸ گیمیفیکیشن

```sql
CREATE TABLE point_rules (
  code          TEXT PRIMARY KEY,      -- 'QUIZ_PASSED', 'MILESTONE_APPROVED', ...
  title_fa      TEXT NOT NULL,
  category      TEXT NOT NULL CHECK (category IN ('LEARNING','RESEARCH','STARTUP','COMMUNITY')),
  base_points   NUMERIC(6,2) NOT NULL,
  formula       TEXT,                  -- توضیح فرمول برای قواعد متغیر
  daily_cap     NUMERIC(6,2),
  term_cap      NUMERIC(6,2),
  is_active     BOOLEAN NOT NULL DEFAULT true,
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE point_entries (           -- دفتر کل تغییرناپذیر (D-09)
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category    TEXT NOT NULL CHECK (category IN ('LEARNING','RESEARCH','STARTUP','COMMUNITY')),
  rule_code   TEXT NOT NULL REFERENCES point_rules(code),
  amount      NUMERIC(6,2) NOT NULL,   -- می‌تواند منفی باشد (رکورد معکوس)
  source_type TEXT NOT NULL,           -- 'QUIZ_ATTEMPT','DELIVERABLE','IDEA_VOTE',...
  source_id   UUID,
  term_id     UUID REFERENCES terms(id),
  offering_id UUID REFERENCES course_offerings(id),
  note        TEXT,
  reverses_id UUID REFERENCES point_entries(id),   -- برای اصلاح
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- جلوگیری از ثبت دوبارهٔ امتیاز برای یک رویداد (FR-GAM-01)
CREATE UNIQUE INDEX idx_point_idempotency
  ON point_entries(user_id, rule_code, source_type, source_id)
  WHERE reverses_id IS NULL AND source_id IS NOT NULL;
CREATE INDEX idx_points_user_term ON point_entries(user_id, term_id, category);
CREATE INDEX idx_points_created ON point_entries(created_at DESC);

CREATE MATERIALIZED VIEW user_point_totals AS
SELECT user_id,
       term_id,
       category,
       SUM(amount) AS total
FROM point_entries
GROUP BY user_id, term_id, category;
CREATE UNIQUE INDEX ON user_point_totals(user_id, term_id, category);

CREATE TABLE badges (
  code        TEXT PRIMARY KEY,
  title_fa    TEXT NOT NULL,
  description TEXT NOT NULL,
  icon        TEXT NOT NULL,
  tier        TEXT NOT NULL CHECK (tier IN ('BRONZE','SILVER','GOLD','PLATINUM')),
  criteria    JSONB NOT NULL,          -- ساختار قابل ارزیابی (§09)
  is_active   BOOLEAN NOT NULL DEFAULT true,
  sort_order  INT NOT NULL DEFAULT 0
);

CREATE TABLE user_badges (
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  badge_code TEXT NOT NULL REFERENCES badges(code),
  awarded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  context    JSONB,                    -- چه چیزی باعث اعطا شد
  PRIMARY KEY (user_id, badge_code)
);
```

---

## ۴.۹ فایل، اعلان، حسابرسی

```sql
CREATE TABLE files (
  id            UUID PRIMARY KEY DEFAULT uuidv7(),
  storage_key   TEXT NOT NULL UNIQUE,        -- کلید در S3
  bucket        TEXT NOT NULL,
  original_name TEXT NOT NULL,
  content_type  TEXT NOT NULL,
  size_bytes    BIGINT NOT NULL CHECK (size_bytes > 0),
  checksum_sha256 TEXT,
  uploaded_by   UUID NOT NULL REFERENCES users(id),
  scan_status   TEXT NOT NULL DEFAULT 'PENDING'
                CHECK (scan_status IN ('PENDING','CLEAN','INFECTED','SKIPPED')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  deleted_at    TIMESTAMPTZ
);
CREATE INDEX idx_files_uploader ON files(uploaded_by, created_at DESC);

CREATE TABLE notifications (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL,            -- 'DELIVERABLE_REVIEWED','QUIZ_OPENED',...
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  action_url TEXT,
  priority   TEXT NOT NULL DEFAULT 'NORMAL'
             CHECK (priority IN ('LOW','NORMAL','IMPORTANT','URGENT')),
  data       JSONB NOT NULL DEFAULT '{}'::jsonb,
  read_at    TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_notifications_unread ON notifications(user_id, created_at DESC)
  WHERE read_at IS NULL;

CREATE TABLE notification_preferences (
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind_group TEXT NOT NULL,            -- 'COURSE','PROJECT','SOCIAL','SYSTEM'
  channels   TEXT[] NOT NULL DEFAULT '{IN_APP}',
  PRIMARY KEY (user_id, kind_group)
);

CREATE TABLE outbox_messages (         -- D-08
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  channel     TEXT NOT NULL CHECK (channel IN ('EMAIL','SMS','TELEGRAM','EITAA','WHATSAPP','PUSH')),
  recipient   TEXT NOT NULL,
  template    TEXT NOT NULL,
  payload     JSONB NOT NULL,
  notification_id UUID REFERENCES notifications(id),
  status      TEXT NOT NULL DEFAULT 'QUEUED'
              CHECK (status IN ('QUEUED','SENDING','SENT','FAILED','DEAD')),
  attempts    INT NOT NULL DEFAULT 0,
  next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_error  TEXT,
  provider_message_id TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  sent_at     TIMESTAMPTZ
);
CREATE INDEX idx_outbox_dispatch ON outbox_messages(next_attempt_at)
  WHERE status IN ('QUEUED','FAILED');

CREATE TABLE message_templates (
  code       TEXT NOT NULL,
  channel    TEXT NOT NULL,
  subject    TEXT,
  body       TEXT NOT NULL,
  variables  TEXT[] NOT NULL DEFAULT '{}',
  is_active  BOOLEAN NOT NULL DEFAULT true,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (code, channel)
);

CREATE TABLE audit_logs (              -- فقط افزودنی (FR-ADM-02)
  id          UUID PRIMARY KEY DEFAULT uuidv7(),
  actor_id    UUID REFERENCES users(id),
  impersonated_by UUID REFERENCES users(id),
  action      TEXT NOT NULL,           -- 'ROLE_GRANTED','GRADE_OVERRIDDEN',...
  entity_type TEXT NOT NULL,
  entity_id   UUID,
  before      JSONB,
  after       JSONB,
  ip_address  INET,
  user_agent  TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id, created_at DESC);
CREATE INDEX idx_audit_actor ON audit_logs(actor_id, created_at DESC);
REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC;

CREATE TABLE app_settings (
  key        TEXT PRIMARY KEY,
  value      JSONB NOT NULL,
  category   TEXT NOT NULL,
  title_fa   TEXT NOT NULL,
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE qa_threads (              -- FR-EDU-07
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  week_id    UUID REFERENCES course_weeks(id) ON DELETE CASCADE,
  offering_id UUID NOT NULL REFERENCES course_offerings(id) ON DELETE CASCADE,
  author_id  UUID NOT NULL REFERENCES users(id),
  is_anonymous BOOLEAN NOT NULL DEFAULT false,
  title      TEXT NOT NULL,
  body       TEXT NOT NULL,
  is_resolved BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE qa_replies (
  id         UUID PRIMARY KEY DEFAULT uuidv7(),
  thread_id  UUID NOT NULL REFERENCES qa_threads(id) ON DELETE CASCADE,
  author_id  UUID NOT NULL REFERENCES users(id),
  body       TEXT NOT NULL,
  is_official BOOLEAN NOT NULL DEFAULT false,   -- پاسخ استاد
  helpful_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE recommendation_feedback (  -- FR-PRJ-03
  user_id    UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  verdict    TEXT NOT NULL CHECK (verdict IN ('NOT_RELEVANT','INTERESTED','DISMISSED')),
  reason     TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, project_id)
);
```

---

## ۴.۱۰ ترتیب مهاجرت‌ها

مهاجرت‌ها باید به این ترتیب ساخته شوند تا وابستگی کلید خارجی نشکند:

```
001_extensions_and_functions   pgcrypto, pg_trgm, unaccent, citext,
                               uuidv7(), fa_normalize(), set_updated_at()
002_identity                   users, roles, user_roles, refresh_tokens, otp_challenges
003_taxonomy                   universities, skills, assets, interests
004_profiles                   profiles, profile_skills/assets/interests, survey_versions
005_files                      files
006_education                  terms, courses, course_offerings, enrollments,
                               course_weeks, resources, resource_progress,
                               class_sessions, attendance_records, announcements
007_quiz                       quizzes, question_bank, quiz_questions,
                               quiz_attempts, quiz_answers, grade_appeals
008_ideas                      ideas, idea_votes, idea_comments
009_ventures                   ventures, venture_metrics
010_projects                   projects, project_required_*, project_roles, project_interests,
                               teams, team_members, project_applications,
                               milestones, deliverables, deliverable_files,
                               project_tasks, project_messages, project_activities,
                               project_reflections, peer_evaluations,
                               certificates, team_openings
                               + قیدهای رو به جلو (announcements, venture_metrics)
011_research                   research_tracks, research_outputs, research_topics
012_gamification               point_rules, point_entries, user_point_totals, badges, user_badges
013_messaging                  notifications, notification_preferences,
                               outbox_messages, message_templates
014_admin                      audit_logs, app_settings, qa_threads, qa_replies,
                               recommendation_feedback
015_seed_reference_data        داده‌های مرجع §14
```

### کلیدهای خارجی با ارجاع رو به جلو

سه ستون به جدولی ارجاع می‌دهند که در مهاجرتی **بعد از** خودشان ساخته می‌شود.
این ستون‌ها بدون قید تعریف می‌شوند و قیدشان در مهاجرت ۰۱۰ افزوده می‌گردد:

```sql
-- در انتهای مهاجرت 010_projects
ALTER TABLE announcements    ADD CONSTRAINT fk_announcements_project
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE venture_metrics  ADD CONSTRAINT fk_venture_metrics_project
  FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE venture_metrics  ADD CONSTRAINT venture_metrics_owner
  CHECK ((venture_id IS NOT NULL)::int + (project_id IS NOT NULL)::int >= 1);
```

> **وابستگی چرخه‌ای:** `projects.venture_id` و `ventures.origin_idea_id` باعث می‌شود
> ترتیب ۰۰۸ → ۰۰۹ → ۰۱۰ الزامی باشد. شکستن این ترتیب، مهاجرت را در محیط تازه
> خراب می‌کند — تست `test_migrations_run_on_empty_database` این را می‌گیرد.

---

## ۴.۱۱ ملاحظات کارایی

| موضوع | راه‌حل |
|-------|--------|
| جدول رتبه‌بندی | `user_point_totals` هر ۱۵ دقیقه `REFRESH MATERIALIZED VIEW CONCURRENTLY` |
| شمارش رأی ایده | ستون غیرنرمال `vote_count` با تریگر — جلوگیری از `COUNT(*)` مکرر |
| جستجوی فارسی | `GIN` روی ستون تولیدشدهٔ نرمال‌شده؛ نه `ILIKE '%…%'` |
| صف بررسی استاد | ایندکس جزئی روی `status IN ('SUBMITTED','UNDER_REVIEW')` |
| موتور توصیه‌گر | محاسبه در SQL با `LATERAL JOIN`، کش ۳۰ دقیقه‌ای در Redis (§08) |
| رشد `point_entries` | پارتیشن‌بندی بر اساس `term_id` وقتی از ۱۰ میلیون ردیف گذشت |
| `audit_logs` | پارتیشن‌بندی ماهانه از ابتدا |

---

## ۴.۱۲ خط‌مشی نگهداری داده

| داده | مدت نگهداری |
|------|-------------|
| `otp_challenges` | ۲۴ ساعت، سپس حذف فیزیکی |
| `refresh_tokens` باطل‌شده | ۹۰ روز |
| `notifications` خوانده‌شده | ۹۰ روز، سپس آرشیو |
| `outbox_messages` ارسال‌شده | ۳۰ روز |
| `audit_logs` | ۷ سال (الزام حسابرسی) |
| داده‌های آموزشی و پروژه | نامحدود (حذف نرم) |
| حساب حذف‌شده | ناشناس‌سازی پس از ۳۰ روز: حذف موبایل/ایمیل/کد ملی، حفظ داده‌های تجمیعی |
