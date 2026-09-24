FROM node:20-alpine AS base
RUN corepack enable && corepack prepare pnpm@10.32.1 --activate

FROM base AS deps
RUN apk add --no-cache libc6-compat
WORKDIR /app
COPY package.json pnpm-lock.yaml* ./
RUN pnpm i --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# 비워 두면 관리자 모니터링 페이지의 Grafana 섹션이 숨겨짐
ARG NEXT_PUBLIC_GRAFANA_URL=
ENV NEXT_PUBLIC_GRAFANA_URL=$NEXT_PUBLIC_GRAFANA_URL

RUN pnpm build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Trivy DS-026 (HEALTHCHECK) 의존 — wget 은 alpine 기본 미포함이지만 BusyBox wget 으로 동작.
# Alpine 의 wget 은 BusyBox 내장이라 별도 install 불필요.

# node:20-alpine 에 내장된 `node` 사용자 (UID 1000) — non-root 로 동작 (Trivy DS-002).
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
# ⚠️ Next.js standalone output 은 public/ 을 자동 복사하지 않음 — 수동 COPY 필수.
# (랜딩 페이지의 /landing/laptop_phone.png 등 정적 에셋이 404 나는 원인이었음)
COPY --from=builder --chown=node:node /app/public ./public

USER node

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD wget -qO- http://localhost:3000 || exit 1

EXPOSE 3000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"
CMD ["node", "server.js"]
