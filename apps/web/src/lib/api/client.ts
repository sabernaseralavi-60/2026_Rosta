/**
 * کلاینت API — قرارداد §5.1.
 *
 * سه مسئولیت، و فقط همین سه:
 *   ۱. تبدیل قالب خطای سرور به یک استثنای تایپ‌دار.
 *   ۲. حمل توکن و انتشار `X-Trace-Id`.
 *   ۳. اعلام نوشتن موفق (`WRITE_EVENT`) — تا امتیاز تازه بی‌درنگ دیده شود.
 *
 * تایپ‌های بدنه از `packages/shared` می‌آیند که از OpenAPI تولید می‌شوند
 * (`make types`) — نه دست‌نویس، تا قرارداد و کد از هم جدا نیفتند.
 */

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
    trace_id: string;
  };
}

/**
 * خطای API با پیام فارسیِ آمادهٔ نمایش.
 *
 * `message` مستقیماً از سرور می‌آید و طبق §5.1 «قابل نمایش مستقیم به
 * کاربر، بدون اصطلاح فنی» است — پس رابط کاربری نباید آن را بازنویسی کند.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  readonly traceId: string;

  constructor(status: number, body: ApiErrorBody['error']) {
    super(body.message);
    this.name = 'ApiError';
    this.status = status;
    this.code = body.code;
    this.details = body.details ?? {};
    this.traceId = body.trace_id ?? '';
  }

  /** خطاهای اعتبارسنجی، به تفکیک فیلد — §5.1. */
  get fieldErrors(): Record<string, string> {
    const fields = this.details.fields;
    return typeof fields === 'object' && fields !== null
      ? (fields as Record<string, string>)
      : {};
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }

  get retryAfterSeconds(): number {
    const value = this.details.retry_after;
    return typeof value === 'number' ? value : 0;
  }
}

/** خطای شبکه — سرور اصلاً پاسخ نداد. */
export class NetworkError extends Error {
  constructor(cause?: unknown) {
    super('ارتباط با سرور برقرار نشد. اتصال اینترنت خود را بررسی کنید.');
    this.name = 'NetworkError';
    this.cause = cause;
  }
}

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? '/api/v1';

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  accessToken?: string | null;
  /** شناسهٔ بی‌اثرسازی برای POSTهای دارای اثر جانبی — §5.1. */
  idempotencyKey?: string;
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, accessToken, idempotencyKey, headers, ...init } = options;

  const requestHeaders = new Headers(headers);
  requestHeaders.set('Accept', 'application/json');
  if (body !== undefined) requestHeaders.set('Content-Type', 'application/json');
  if (accessToken) requestHeaders.set('Authorization', `Bearer ${accessToken}`);
  if (idempotencyKey) requestHeaders.set('Idempotency-Key', idempotencyKey);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (cause) {
    throw new NetworkError(cause);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload: unknown = text ? safeParse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, extractError(payload, response));
  }

  if (init.method && init.method.toUpperCase() !== 'GET') announceWrite();
  return payload as T;
}

/**
 * رویداد «نوشتنی موفق انجام شد» — M5.
 *
 * هر نوشتن ممکن است امتیاز داده باشد: تأیید مرحله، ارسال آزمون، «خواندم».
 * به‌جای اینکه هر صفحه جداگانه هدر را خبر کند، کلاینت API یک بار اعلام
 * می‌کند و `PointsBadge` (§9.10 «فوریت») گوش می‌دهد.
 */
export const WRITE_EVENT = 'silp:write';

function announceWrite(): void {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new Event(WRITE_EVENT));
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/**
 * استخراج خطا از پاسخ.
 *
 * اگر پاسخ قالب مورد انتظار را نداشت (مثلاً صفحهٔ خطای Nginx)، یک خطای
 * عمومی فارسی ساخته می‌شود — کاربر نباید HTML خام ببیند.
 */
function extractError(payload: unknown, response: Response): ApiErrorBody['error'] {
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'error' in payload &&
    typeof (payload as ApiErrorBody).error?.code === 'string'
  ) {
    return (payload as ApiErrorBody).error;
  }

  return {
    code: 'UNEXPECTED_RESPONSE',
    message: 'پاسخ غیرمنتظره‌ای از سرور دریافت شد. کمی بعد دوباره تلاش کنید.',
    details: {},
    trace_id: response.headers.get('X-Trace-Id') ?? '',
  };
}
