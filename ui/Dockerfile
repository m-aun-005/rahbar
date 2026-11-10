# Pinned unprivileged nginx base image (section 4.7 & check_dockerfiles)
FROM nginxinc/nginx-unprivileged:1.27-alpine

# Apply available Alpine security fixes in the pinned base image.
RUN apk upgrade --no-cache

# Copy custom nginx configuration for non-root execution (listening on 8080)
COPY nginx.conf /etc/nginx/nginx.conf

# Copy chat UI static assets
COPY index.html /usr/share/nginx/html/index.html

# Run as non-root unprivileged nginx user (UID 101)
USER 101

EXPOSE 8080

# Exec-form CMD
CMD ["nginx", "-g", "daemon off;"]
