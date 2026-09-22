import type { NextConfig } from 'next';

/**
 * پیکربندی Next.js — PRD §12.
 *
 * هدرهای امنیتی در تولید توسط Nginx هم گذاشته می‌شوند (NFR-03)؛ تکرارشان
 * اینجا برای محیط توسعه و برای حالتی است که اپ بدون پروکسی اجرا شود.
 */
const securityHeaders = [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(self)',
  },
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // خروجی standalone تا ایمیج تولید کوچک بماند. فقط در ساخت ایمیج
  // فعال است: ساخت standalone روی ویندوز به دسترسی ساخت symlink نیاز
  // دارد که به‌صورت پیش‌فرض وجود ندارد، و توسعه‌دهنده را بی‌دلیل مسدود
  // می‌کند. Dockerfile این متغیر را می‌گذارد.
  output: process.env.NEXT_OUTPUT === 'standalone' ? 'standalone' : undefined,
  outputFileTracingRoot: '../..',

  // مسیرهای تایپ‌دار: `<Link href="/typo">` خطای کامپایل می‌دهد.
  //
  // به همین دلیل `pnpm dev` بدون `--turbopack` اجرا می‌شود: Turbopack در
  // Next 15.1 این گزینه را پشتیبانی نمی‌کند و با آن اصلاً بالا نمی‌آید.
  // ایمنی تایپ مسیرها به سرعت بازسازی در توسعه می‌ارزد.
  experimental: {
    typedRoutes: true,
  },

  eslint: {
    // لینت در CI به‌صورت جداگانه اجرا می‌شود؛ تکرارش build را کند می‌کند.
    ignoreDuringBuilds: true,
  },

  async headers() {
    return [{ source: '/:path*', headers: securityHeaders }];
  },

  async rewrites() {
    // مرورگر مستقیم با API حرف می‌زند؛ این فقط برای توسعه است تا
    // CORS و کوکی‌ها دردسر نسازند.
    const target = process.env.INTERNAL_API_URL ?? 'http://localhost:8000/api/v1';
    return [{ source: '/api/v1/:path*', destination: `${target}/:path*` }];
  },
};

export default nextConfig;
