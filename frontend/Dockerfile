# =============================================================================
#  Recipe for the FRONTEND image (the web page)
# =============================================================================
#  Two stages:
#   1. "build": a Node.js machine turns our React code (frontend/src/*.jsx)
#      into plain HTML/CSS/JavaScript files that any browser understands.
#   2. a tiny nginx web server that only contains those finished files.
#      Node.js and the source code are NOT in the final image.
#
#  Used by the "frontend" container in docker-compose.yml (server port 20800).
# =============================================================================

# ---- Stage 1: build the web page ----
FROM node:22-alpine AS build
WORKDIR /app
# Install the JavaScript libraries listed in package.json (exact versions from package-lock.json).
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
# Copy our code and build it. The result lands in /app/dist.
COPY . .
RUN npm run build

# ---- Stage 2: serve the finished files with nginx ----
FROM nginx:1.27-alpine
# Our nginx settings: serve the page + forward /api/... to the api container.
COPY nginx.conf /etc/nginx/conf.d/default.conf
# The built web page from stage 1 -> nginx's web folder.
COPY --from=build /app/dist /usr/share/nginx/html
# nginx listens on port 80 inside the container (server port 20800, see docker-compose.yml).
EXPOSE 80
