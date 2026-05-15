FROM node:22-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# Build-time env vars baked into the bundle
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
ARG VITE_QZ_PRIVATE_KEY
ENV VITE_QZ_PRIVATE_KEY=$VITE_QZ_PRIVATE_KEY
ARG VITE_SSO_ENABLED
ENV VITE_SSO_ENABLED=$VITE_SSO_ENABLED
ARG VITE_ENV=prod
ENV VITE_ENV=$VITE_ENV

RUN npx vite build

# ── Serve with nginx ─────────────────────────────────────────────────────────
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
CMD ["nginx", "-g", "daemon off;"]
