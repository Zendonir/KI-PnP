# syntax=docker/dockerfile:1
FROM node:22-alpine AS build

WORKDIR /app
ENV CI=1

COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY tsconfig*.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src

ARG VITE_API_BASE=/api/v1
ENV VITE_API_BASE=$VITE_API_BASE
ARG VITE_APP_VERSION=0.0.0-dev
ENV VITE_APP_VERSION=$VITE_APP_VERSION
ARG VITE_GIT_SHA=dev
ENV VITE_GIT_SHA=$VITE_GIT_SHA
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/ >/dev/null || exit 1
