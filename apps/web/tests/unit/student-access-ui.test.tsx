import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { StudentAccess } from '@/app/(auth)/student/StudentAccess';

/** ورود دانشجوی درس با موبایل + شمارهٔ دانشجویی — ADR-0035. */

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace, prefetch: vi.fn() }),
}));

const LOGIN = {
  access_token: 'a',
  refresh_token: 'r',
  token_type: 'bearer',
  expires_in: 900,
  user: {
    id: 'u1',
    display_name: null,
    username: null,
    roles: ['STUDENT'],
    onboarding_state: 'SURVEY_REQUIRED',
  },
  is_new_user: true,
  courses: ['مهندسی ترابری'],
};

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function stubFetch(...responses: Response[]) {
  const fetchMock = vi.fn();
  for (const response of responses) fetchMock.mockResolvedValueOnce(response);
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => replace.mockClear());
afterEach(() => vi.unstubAllGlobals());

async function fillLookup() {
  await userEvent.type(screen.getByLabelText('شمارهٔ موبایل'), '۰۹۱۲۱۲۳۴۵۶۷');
  await userEvent.type(screen.getByLabelText('شمارهٔ دانشجویی'), '۴۰۲۱۲۳۴۵۶');
  await userEvent.click(screen.getByRole('button', { name: 'ادامه' }));
}

describe('فعال‌سازی حساب دانشجو', () => {
  it('شمارهٔ دانشجویی رمز نیست و صریحاً همین گفته می‌شود', () => {
    render(<StudentAccess />);
    expect(screen.getByText(/رمز تو نیست/)).toBeInTheDocument();
  });

  it('ارقام فارسی لاتین می‌شوند و فقط نام پوشیده نشان داده می‌شود', async () => {
    const fetchMock = stubFetch(
      json(200, { claim_id: 'c1', display_name: 'علی ر.', has_email: true }),
    );
    render(<StudentAccess />);
    await fillLookup();

    expect(await screen.findByText('علی ر.')).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({
      mobile: '09121234567',
      student_no: '402123456',
    });
  });

  it('مسیر کامل: تأیید هویت ← کد و رمز ← ذخیرهٔ نشست و رفتن به پرسشنامه', async () => {
    stubFetch(
      json(200, { claim_id: 'c1', display_name: 'علی ر.', has_email: true }),
      json(200, {
        cancelled: false,
        masked_email: 'a***@eng.example.ac.ir',
        expires_in: 600,
        resend_after: 60,
      }),
      json(200, LOGIN),
    );
    render(<StudentAccess />);
    await fillLookup();
    await userEvent.click(await screen.findByRole('button', { name: 'بله، من هستم' }));

    expect(await screen.findByText('a***@eng.example.ac.ir')).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText('کد ایمیل'), '111111');
    await userEvent.type(screen.getByLabelText('رمز تازه'), 'Kerman-1405-safe');
    await userEvent.click(screen.getByRole('button', { name: 'فعال‌سازی و ورود' }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/onboarding/survey/1'));
    expect(sessionStorage.length).toBeGreaterThan(0);
  });

  it('بدون ایمیل در فهرست، دکمهٔ تأیید غیرفعال است و به استاد ارجاع می‌دهد', async () => {
    stubFetch(json(200, { claim_id: 'c1', display_name: 'سارا ک.', has_email: false }));
    render(<StudentAccess />);
    await fillLookup();

    expect(await screen.findByRole('button', { name: 'بله، من هستم' })).toBeDisabled();
    expect(screen.getByText(/به استاد بگو/)).toBeInTheDocument();
  });

  it('شمارهٔ ناموجود پیام سرور را نشان می‌دهد و در همان گام می‌ماند', async () => {
    stubFetch(
      json(404, { error: { code: 'ROSTER_NOT_FOUND', message: 'این شمارهٔ دانشجویی پیدا نشد.' } }),
    );
    render(<StudentAccess />);
    await fillLookup();

    expect(await screen.findByText('این شمارهٔ دانشجویی پیدا نشد.')).toBeInTheDocument();
    expect(screen.getByLabelText('شمارهٔ دانشجویی')).toBeInTheDocument();
  });

  it('«نه» درخواست را لغو می‌کند و به گام اول برمی‌گردد', async () => {
    const fetchMock = stubFetch(
      json(200, { claim_id: 'c1', display_name: 'علی ر.', has_email: true }),
      json(200, { cancelled: true, masked_email: null, expires_in: 0, resend_after: 0 }),
    );
    render(<StudentAccess />);
    await fillLookup();
    await userEvent.click(await screen.findByRole('button', { name: 'نه' }));

    expect(await screen.findByLabelText('شمارهٔ دانشجویی')).toBeInTheDocument();
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ claim_id: 'c1', accept: false });
  });
});

describe('ورود با رمز', () => {
  it('موبایل و رمز به /auth/login می‌رود و نشست ذخیره می‌شود', async () => {
    const fetchMock = stubFetch(
      json(200, { ...LOGIN, user: { ...LOGIN.user, onboarding_state: 'COMPLETE' } }),
    );
    render(<StudentAccess />);
    await userEvent.click(screen.getByRole('button', { name: 'ورود با رمز' }));
    await userEvent.type(screen.getByLabelText('شمارهٔ موبایل'), '۰۹۱۲۱۲۳۴۵۶۷');
    await userEvent.type(screen.getByLabelText('رمز عبور'), 'Kerman-1405-safe');
    await userEvent.click(screen.getByRole('button', { name: 'ورود' }));

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/dashboard'));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/auth/login');
    expect(JSON.parse(String(init.body))).toEqual({
      identifier: '09121234567',
      password: 'Kerman-1405-safe',
    });
  });

  it('رمز اشتباه پیام سرور را نشان می‌دهد', async () => {
    stubFetch(
      json(401, {
        error: { code: 'INVALID_CREDENTIALS', message: 'نام کاربری یا رمز عبور نادرست است.' },
      }),
    );
    render(<StudentAccess />);
    await userEvent.click(screen.getByRole('button', { name: 'ورود با رمز' }));
    await userEvent.type(screen.getByLabelText('شمارهٔ موبایل'), '09121234567');
    await userEvent.type(screen.getByLabelText('رمز عبور'), 'wrong-password');
    await userEvent.click(screen.getByRole('button', { name: 'ورود' }));

    expect(await screen.findByText('نام کاربری یا رمز عبور نادرست است.')).toBeInTheDocument();
    expect(replace).not.toHaveBeenCalled();
  });
});
