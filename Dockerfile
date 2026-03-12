# ==============================================================================
# ADG Knowledge Management System - Production Dockerfile
# ==============================================================================

FROM python:3.13-slim

# System dependencies + cleanup in same layer to reduce size
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove gcc \
    || true

# Copy only what's needed (not entire repo)
COPY backend/ ./backend/
COPY frontend/ ./frontend/

ENV PORT=8080
EXPOSE 8080

# Use Python startup script instead of bash (avoids CRLF line ending issues)
CMD ["python", "-m", "backend.startup"]
