import type { MetadataRoute } from 'next';

/**
 * مانیفست برنامهٔ وب — ADR-0029.
 *
 * `start_url` داشبورد است؛ کاربر بی‌نشست از آنجا به ورود می‌رود و پس از ورود
 * برمی‌گردد. `theme_color` همان `--brand-600` است (oklch(54% 0.114 182)).
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: 'سامانهٔ نوآوری و یادگیری صابر',
    short_name: 'سیلپ',
    description: 'یادگیری، پژوهش، کارآفرینی و حل مسئلهٔ واقعی — یک‌جا.',
    lang: 'fa',
    dir: 'rtl',
    start_url: '/dashboard',
    scope: '/',
    display: 'standalone',
    orientation: 'portrait',
    background_color: '#fafaf9',
    theme_color: '#008374',
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      {
        src: '/icons/icon-maskable-512.png',
        sizes: '512x512',
        type: 'image/png',
        purpose: 'maskable',
      },
    ],
  };
}
