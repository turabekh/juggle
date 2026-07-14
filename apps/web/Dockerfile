# syntax=docker/dockerfile:1
# Production frontend image: build the Quasar SPA, then serve it with Caddy.
# Caddy serves the static bundle with SPA history fallback and reverse-proxies
# /api/* to the API service. It auto-provisions HTTPS when DOMAIN is a real
# hostname (ports 80/443 reachable + DNS pointed at the host); otherwise it
# serves plain HTTP on :80. See apps/web/Caddyfile.

# --- Build stage ---------------------------------------------------------
FROM node:20-slim AS build
WORKDIR /app

# Install deps first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

# Build the client bundle (vue-tsc typecheck + vite build → dist/).
COPY . .
RUN npm run build

# --- Serve stage ---------------------------------------------------------
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
EXPOSE 80 443
