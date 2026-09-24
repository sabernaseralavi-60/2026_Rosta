import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

/**
 * نشست هر نقش یک بار، پیش از همهٔ تست‌ها — M7-14.
 *
 * ممیزی دسترس‌پذیری ده‌ها صفحهٔ واردشده را در دو تم باز می‌کند؛ ورود از
 * رابط برای هر صفحه هم کند است و هم از سقف `OTP_PER_IP_PER_HOUR` (۱۰)
 * می‌گذرد. پس هر نقش یک بار از راه API وارد می‌شود و توکن در
 * `sessionStorage` صفحه تزریق می‌شود — همان کلیدهای `lib/auth/session.ts`.
 *
 * هر نقش از «IP» جدای خودش وارد می‌شود (`X-Forwarded-For`): در CI پروکسی
 * جلوی API نیست و سقف ورود بقیهٔ تست‌ها نباید خرج این‌ها شود.
 */

export const ROLES = {
  student: '09120000010',
  admin: '09120000001',
} as const;

export type Role = keyof typeof ROLES;

export interface StoredSession {
  access_token: string;
  refresh_token: string;
  user: unknown;
}

const HERE = dirname(fileURLToPath(import.meta.url));
export const SESSIONS_FILE = join(HERE, '.auth', 'sessions.json');

const API = process.env.E2E_API_URL ?? 'http://localhost:8000/api/v1';
const DEV_OTP = '111111';

async function login(mobile: string, ip: string): Promise<StoredSession> {
  const headers = { 'Content-Type': 'application/json', 'X-Forwarded-For': ip };
  const requested = await fetch(`${API}/auth/otp/request`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ destination: mobile, channel: 'SMS' }),
  });
  if (!requested.ok) throw new Error(`OTP request ${mobile}: HTTP ${requested.status}`);
  const { challenge_id } = (await requested.json()) as { challenge_id: string };

  const verified = await fetch(`${API}/auth/otp/verify`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ challenge_id, code: DEV_OTP }),
  });
  if (!verified.ok) throw new Error(`OTP verify ${mobile}: HTTP ${verified.status}`);
  return (await verified.json()) as StoredSession;
}

export default async function globalSetup(): Promise<void> {
  const sessions: Partial<Record<Role, StoredSession>> = {};
  let octet = 10;
  for (const [role, mobile] of Object.entries(ROLES) as [Role, string][]) {
    sessions[role] = await login(mobile, `10.99.0.${octet}`);
    octet += 1;
  }
  await mkdir(dirname(SESSIONS_FILE), { recursive: true });
  await writeFile(SESSIONS_FILE, JSON.stringify(sessions));
}
