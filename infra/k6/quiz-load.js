/**
 * آزمون بار آزمون — NFR-07، وظیفهٔ نقشهٔ راه M4-16.
 *
 * **چرا این تست وجود دارد:** ظرفیت هدف فاز ۱، «۱۵۰ دانشجوی هم‌زمان در
 * آزمون» است. این عدد جایی است که سامانه واقعاً زیر فشار می‌رود — نه
 * صفحهٔ فهرست دروس، که کسی هم‌زمان بازش نمی‌کند.
 *
 * سناریو، همان کاری است که یک دانشجو در آزمون می‌کند و نه چیز دیگر:
 *
 *   ۱. ورود با OTP توسعه
 *   ۲. شروع تلاش
 *   ۳. خواندن سؤالات
 *   ۴. **ذخیرهٔ خودکار هر ۱۰ ثانیه** — سنگین‌ترین بخش: ۱۵۰ نفر × هر
 *      ۱۰ ثانیه یک `PUT` یعنی ۱۵ درخواست در ثانیه فقط برای ذخیره
 *   ۵. ارسال نهایی
 *
 * ## اجرا
 *
 * ```bash
 * # پشتهٔ تست باید بالا باشد و آزمون آماده (اسکریپت seed را ببینید)
 * k6 run -e BASE_URL=http://localhost:8000 -e QUIZ_ID=<uuid> infra/k6/quiz-load.js
 * ```
 *
 * ## چرا شماره‌های موبایل ساختگی‌اند
 *
 * هر VU با شمارهٔ خودش وارد می‌شود (`0912` + شمارهٔ VU) تا قید
 * `idx_one_active_attempt` واقعی آزموده شود: اگر همه با یک حساب وارد
 * می‌شدند، ۱۴۹ نفر `ACTIVE_ATTEMPT_EXISTS` می‌گرفتند و تست بار، بارِ
 * واقعی را اندازه نمی‌گرفت.
 */

import { check, sleep } from 'k6';
import http from 'k6/http';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const QUIZ_ID = __ENV.QUIZ_ID;
const DEV_OTP = __ENV.DEV_OTP || '111111';
const API = `${BASE_URL}/api/v1`;

const saveLatency = new Trend('answer_save_duration', true);
const saveFailures = new Rate('answer_save_failed');
const startFailures = new Rate('attempt_start_failed');

export const options = {
  scenarios: {
    exam: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        // ورود تدریجی، چون در آزمون واقعی هم همه در یک ثانیه نمی‌آیند.
        { duration: '30s', target: 50 },
        { duration: '30s', target: 150 },
        // ظرفیت هدف NFR-07، نگه‌داشته‌شده برای سه دقیقه.
        { duration: '3m', target: 150 },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
  },
  thresholds: {
    // §11 — «p95 زیر ۵۰۰ms برای نوشتن». ذخیرهٔ پاسخ باید از این
    // سخت‌گیرانه‌تر باشد، چون هر ۱۰ ثانیه تکرار می‌شود.
    answer_save_duration: ['p(95)<400'],
    answer_save_failed: ['rate<0.01'],
    attempt_start_failed: ['rate<0.01'],
    http_req_failed: ['rate<0.02'],
  },
};

export function setup() {
  if (!QUIZ_ID) {
    throw new Error('QUIZ_ID لازم است: k6 run -e QUIZ_ID=<uuid> …');
  }
  return { quizId: QUIZ_ID };
}

function login(mobile) {
  const requested = http.post(
    `${API}/auth/otp/request`,
    JSON.stringify({ destination: mobile, channel: 'SMS' }),
    { headers: { 'Content-Type': 'application/json' }, tags: { step: 'otp_request' } },
  );
  if (requested.status !== 200) return null;

  const verified = http.post(
    `${API}/auth/otp/verify`,
    JSON.stringify({ challenge_id: requested.json('challenge_id'), code: DEV_OTP }),
    { headers: { 'Content-Type': 'application/json' }, tags: { step: 'otp_verify' } },
  );
  if (verified.status !== 200) return null;
  return verified.json('access_token');
}

export default function exam(data) {
  // شمارهٔ یکتا به‌ازای هر VU — قید «یک تلاش فعال» واقعاً آزموده شود.
  const mobile = `0912${String(1000000 + __VU).slice(0, 7)}`;
  const token = login(mobile);
  if (!token) {
    startFailures.add(1);
    return;
  }
  const auth = {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  };

  // ── شروع تلاش ──────────────────────────────────────────────────────
  const started = http.post(`${API}/quizzes/${data.quizId}/attempts`, null, {
    ...auth,
    tags: { step: 'start' },
  });
  const ok = check(started, { 'تلاش شروع شد': (r) => r.status === 201 });
  startFailures.add(!ok);
  if (!ok) return;

  const attemptId = started.json('attempt_id');

  // ── خواندن سؤالات ──────────────────────────────────────────────────
  const view = http.get(`${API}/attempts/${attemptId}`, { ...auth, tags: { step: 'view' } });
  check(view, {
    'سؤالات آمد': (r) => r.status === 200,
    // الزام امنیتی §5.6 — زیر بار هم کلید پاسخ نباید بیرون بیاید.
    'کلید پاسخ نشت نکرد': (r) => !r.body.includes('"correct"'),
  });
  if (view.status !== 200) return;

  const questions = view.json('questions') || [];

  // ── ذخیرهٔ خودکار — سنگین‌ترین بخش ────────────────────────────────
  for (let index = 0; index < questions.length; index += 1) {
    const question = questions[index];
    const response = answerFor(question);
    if (response) {
      const saved = http.put(
        `${API}/attempts/${attemptId}/answers/${question.id}`,
        JSON.stringify({ response, client_ts: new Date().toISOString() }),
        { ...auth, tags: { step: 'save' } },
      );
      saveLatency.add(saved.timings.duration);
      saveFailures.add(saved.status !== 200);
      check(saved, { 'پاسخ ذخیره شد': (r) => r.status === 200 });
    }
    // فاصلهٔ ذخیرهٔ خودکار (FR-QUIZ-02) — نه سریع‌تر، که بار مصنوعی
    // شود؛ نه کندتر، که بار واقعی دیده نشود.
    sleep(10);
  }

  // ── ارسال نهایی ────────────────────────────────────────────────────
  const submitted = http.post(
    `${API}/attempts/${attemptId}/submit`,
    JSON.stringify({ confirm_unanswered: 0 }),
    { ...auth, tags: { step: 'submit' } },
  );
  check(submitted, { 'ارسال شد': (r) => r.status === 200 });
}

/** پاسخ ساختگی متناسب با نوع سؤال. */
function answerFor(question) {
  const options = (question.payload && question.payload.options) || [];
  switch (question.kind) {
    case 'SINGLE_CHOICE':
      return options.length ? { selected: [options[0].id] } : null;
    case 'MULTI_CHOICE':
      return options.length ? { selected: options.slice(0, 2).map((o) => o.id) } : null;
    case 'TRUE_FALSE':
      return { value: true };
    case 'SHORT_ANSWER':
      return { text: 'پاسخ کوتاه آزمایشی' };
    case 'NUMERIC':
      return { value: '12.5' };
    case 'ESSAY':
      return { text: 'پاسخ تشریحی آزمایشی برای سنجش بار سامانه.' };
    default:
      return null;
  }
}
