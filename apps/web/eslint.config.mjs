import nextPlugin from '@next/eslint-plugin-next';
import reactPlugin from 'eslint-plugin-react';
import hooksPlugin from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

/**
 * پیکربندی ESLint — NFR-17، §10.5.
 *
 * از `eslint-config-next` استفاده نمی‌شود: آن بسته هنوز از طریق
 * `@rushstack/eslint-patch` به نسخه‌های قدیمی ESLint وصل می‌شود و با
 * flat config نسخهٔ ۹ می‌شکند. افزونه‌ها مستقیم آورده شده‌اند.
 */

/**
 * قاعدهٔ سخت‌گیرانهٔ RTL — §10.5.
 *
 * «هرگز از left و right استفاده نکنید.» کلاس‌های فیزیکی Tailwind در یک
 * رابط RTL بی‌صدا می‌شکنند: در انگلیسی درست به نظر می‌رسند و در فارسی
 * وارونه‌اند. این قاعده آن‌ها را **خطا** اعلام می‌کند، نه هشدار.
 */
const PHYSICAL_CLASS =
  String.raw`(^|\s)-?(m|p)(l|r)-|` +
  String.raw`(^|\s)text-(left|right)(\s|$)|` +
  String.raw`(^|\s)border-(l|r)-|` +
  String.raw`(^|\s)(left|right)-\d|` +
  String.raw`(^|\s)rounded-(tl|tr|bl|br)-`;

const RTL_MESSAGE =
  'کلاس فیزیکی در رابط RTL ممنوع است (§10.5): به‌جای ml-/mr- از ms-/me-، ' +
  'به‌جای text-left/right از text-start/end، و به‌جای left-/right- از start-/end- ' +
  'استفاده کنید.';

export default tseslint.config(
  {
    // خود این فایل الگوی کلاس‌های ممنوع را به‌صورت رشته دارد و
    // در غیر این صورت قاعده روی خودش شلیک می‌کند.
    ignores: [
      '.next/**',
      'node_modules/**',
      'next-env.d.ts',
      'playwright-report/**',
      'eslint.config.mjs',
    ],
  },

  ...tseslint.configs.recommended,

  {
    files: ['**/*.{ts,tsx,mjs}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    plugins: {
      '@next/next': nextPlugin,
      react: reactPlugin,
      'react-hooks': hooksPlugin,
    },
    settings: { react: { version: 'detect' } },
    rules: {
      ...nextPlugin.configs.recommended.rules,
      ...nextPlugin.configs['core-web-vitals'].rules,
      ...hooksPlugin.configs.recommended.rules,

      // §10.5 — جهت
      'no-restricted-syntax': [
        'error',
        { selector: `Literal[value=/${PHYSICAL_CLASS}/]`, message: RTL_MESSAGE },
        {
          selector: `TemplateElement[value.raw=/${PHYSICAL_CLASS}/]`,
          message: RTL_MESSAGE,
        },
      ],

      // NFR-02 — XSS: محتوای Markdown با rehype-sanitize، نه تزریق خام.
      'react/no-danger': 'error',

      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/consistent-type-imports': [
        'error',
        { prefer: 'type-imports', fixStyle: 'inline-type-imports' },
      ],
    },
  },

  {
    // تست‌ها متن نمونه دارند و مشمول قاعدهٔ RTL نیستند.
    files: ['tests/**', '**/*.test.{ts,tsx}'],
    rules: { 'no-restricted-syntax': 'off' },
  },
);
