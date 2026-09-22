# SILP API — ایمیج چندمرحله‌ای
# مرحلهٔ dev برای توسعهٔ محلی (با uv و وابستگی‌های dev)،
# مرحلهٔ runtime برای تولید (بدون ابزار ساخت).

# ── پایه ──────────────────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    TZ=Asia/Tehran
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /usr/local/bin/
WORKDIR /app

# ── وابستگی‌ها ────────────────────────────────────────────────────────
FROM base AS deps
COPY apps/api/pyproject.toml /app/apps/api/pyproject.toml
WORKDIR /app/apps/api
RUN uv venv /app/.venv \
 && uv pip install --python /app/.venv/bin/python -r pyproject.toml --extra dev

# ── توسعه ─────────────────────────────────────────────────────────────
FROM deps AS dev
ENV PYTHONPATH=/app/apps/api/src
COPY apps/api /app/apps/api
COPY infra /app/infra
RUN chmod +x /app/infra/scripts/*.sh 2>/dev/null || true
WORKDIR /app/apps/api
EXPOSE 8000
CMD ["uvicorn", "silp.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

# ── تولید ─────────────────────────────────────────────────────────────
FROM base AS runtime
ENV PYTHONPATH=/app/apps/api/src
COPY --from=deps /app/.venv /app/.venv
# وابستگی‌های dev در تولید لازم نیستند.
RUN uv pip uninstall --python /app/.venv/bin/python \
      pytest pytest-asyncio pytest-cov hypothesis ruff mypy 2>/dev/null || true
COPY apps/api /app/apps/api
COPY infra /app/infra
RUN groupadd --system silp && useradd --system --gid silp --home /app silp \
 && chown -R silp:silp /app
USER silp
WORKDIR /app/apps/api
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "silp.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
