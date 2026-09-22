# SILP Web — ایمیج چندمرحله‌ای Next.js 15

FROM node:22-alpine AS base
ENV PNPM_HOME=/pnpm \
    PATH=/pnpm:$PATH \
    NEXT_TELEMETRY_DISABLED=1
RUN corepack enable && apk add --no-cache libc6-compat
WORKDIR /app

# ── وابستگی‌ها ────────────────────────────────────────────────────────
FROM base AS deps
COPY package.json pnpm-lock.yaml* pnpm-workspace.yaml .npmrc ./
COPY apps/web/package.json apps/web/
COPY packages/shared/package.json packages/shared/
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile || pnpm install

# ── توسعه ─────────────────────────────────────────────────────────────
FROM deps AS dev
COPY . .
EXPOSE 3000
CMD ["pnpm", "--filter", "web", "dev"]

# ── ساخت ──────────────────────────────────────────────────────────────
FROM deps AS builder
ENV NEXT_OUTPUT=standalone
COPY . .
# قلم Vazirmatn در مخزن نیست و در زمان ساخت دریافت می‌شود (§10.3).
RUN pnpm --filter web build

# ── تولید ─────────────────────────────────────────────────────────────
FROM base AS runtime
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# خروجی standalone فقط وابستگی‌های واقعاً استفاده‌شده را حمل می‌کند.
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/.next/static ./apps/web/.next/static
COPY --from=builder --chown=nextjs:nodejs /app/apps/web/public ./apps/web/public

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://localhost:3000/login').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
