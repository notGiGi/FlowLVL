# Build stage
FROM node:16-alpine AS build

WORKDIR /app

# Copy package files and install dependencies
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci

# Copy source code and build
COPY dashboard/public ./public
COPY dashboard/src ./src
COPY dashboard/.env* ./

# Build app
RUN npm run build

# Serve stage
FROM nginx:1.23-alpine

# Copy built files from build stage
COPY --from=build /app/build /usr/share/nginx/html

# Copy nginx configuration
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf

# Script to replace environment variables at runtime
COPY dashboard/docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

# Replace environment variables in JS files at runtime
ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]