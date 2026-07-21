# syntax=docker/dockerfile:1
# Production frontend image: build the SSR bundles (client + server) and serve
# them with the request-time SSR server (server.mjs). Caddy sits in front for TLS
# and reverse-proxies here (see docker-compose.prod.yml + apps/web/Caddyfile).
# On any SSR render error server.mjs falls back to the SPA shell, so the site
# degrades to client-render rather than breaking.

# --- Build stage ---------------------------------------------------------
FROM node:20-slim AS build
WORKDIR /app

# VITE_* are inlined at build time. The SSR server calls the API in-container and
# builds absolute canonical URLs from the public origin.
ARG VITE_SSR_API_BASE=http://api:8000/api/v1
ARG VITE_PUBLIC_ORIGIN=https://kidspots.store
ENV VITE_SSR_API_BASE=$VITE_SSR_API_BASE
ENV VITE_PUBLIC_ORIGIN=$VITE_PUBLIC_ORIGIN

# Install deps first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build dist/client (hydration bundle) + dist/server (renderToString bundle).
COPY . .
RUN npm run build:ssr

# --- Runtime stage -------------------------------------------------------
# entry-server.js externalises vue/pinia/vue-router, so node_modules is needed
# at runtime; server.mjs (prod path) does not import vite.
FROM node:20-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=5173
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/server.mjs ./server.mjs
EXPOSE 5173
CMD ["node", "server.mjs"]
