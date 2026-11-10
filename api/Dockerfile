# Pinned base image (section 4.7 & check_dockerfiles)
FROM python:3.12-slim

# Prevent Python from writing .pyc files and enable unbuffered output for JSON logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Create dedicated non-root user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /sbin/nologin -M appuser

# Install pinned dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY app/ ./app/

# Set ownership and drop root privileges
RUN chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

# Exec-form CMD ensures PID 1 receives Kubernetes SIGTERM signals cleanly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
