# Pinned base image (section 4.7 & check_dockerfiles)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system libraries required for OCR (tesseract-ocr) and PDF image rasterization (poppler-utils)
RUN apt-get update && \
    apt-get upgrade -y --no-install-recommends && \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 10002 indexergroup && \
    useradd -u 10002 -g indexergroup -s /sbin/nologin -M indexer

# Install pinned dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline source code
COPY pipeline/ ./pipeline/

# Prepare directories and transfer ownership
RUN mkdir -p /tmp/indexer && \
    chown -R indexer:indexergroup /app /tmp/indexer
USER indexer

# Exec-form CMD
CMD ["python", "-m", "pipeline.run"]
