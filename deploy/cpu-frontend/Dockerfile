# ==============================================================================
# CPU Frontend Multi-Stage Dockerfile (Node 20 build -> Nginx alpine)
# ==============================================================================

# Stage 1: Build the Vite React Single-Page Application
FROM node:20-alpine AS builder

WORKDIR /app

# Build arguments for frontend configuration
# If empty, frontend uses relative URLs and routes through the Nginx reverse proxy
ARG VITE_API_BASE_URL=""
ARG VITE_WS_URL=""

ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_WS_URL=$VITE_WS_URL

# Install dependencies first (leverages Docker layer cache)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source code and config
COPY index.html vite.config.js ./
COPY public ./public
COPY src ./src

# Compile production bundle into /app/dist
RUN npm run build

# Stage 2: Serve compiled static files with Nginx
FROM nginx:1.27-alpine

# Remove default static files
RUN rm -rf /usr/share/nginx/html/*

# Copy compiled files from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy Nginx configuration template (envsubst will populate $BACKEND_URL at startup)
COPY deploy/cpu-frontend/default.conf.template /etc/nginx/templates/default.conf.template
COPY deploy/cpu-frontend/nginx.conf /etc/nginx/nginx.conf.example
COPY deploy/cpu-frontend/nginx-ssl.conf /etc/nginx/nginx-ssl.conf.example

# Default GPU backend URL fallback
ENV BACKEND_URL="http://localhost:8000"

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://localhost:80/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
