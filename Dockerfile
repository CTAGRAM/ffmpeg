# FFmpeg API Service - Optimized for Koyeb Free Tier (256MB RAM)
# Uses Alpine for minimal image size

FROM python:3.11-alpine

# Install FFmpeg and dependencies
RUN apk add --no-cache \
    ffmpeg \
    libass \
    && rm -rf /var/cache/apk/*

# Set working directory
WORKDIR /app

# Copy requirements first (for Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Create work directory
RUN mkdir -p /tmp/ffmpeg_work

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8000/health || exit 1

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "600", "app:app"]
