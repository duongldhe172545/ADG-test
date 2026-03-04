# ==============================================================================
# ADG Knowledge Management System - Production Dockerfile
# ==============================================================================

FROM python:3.13-slim

# System dependencies for psycopg2, PyMuPDF, and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies first (for Docker layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Copy startup script
COPY start.sh .
RUN chmod +x start.sh

# Default port (Railway overrides via $PORT env var)
ENV PORT=8080
EXPOSE 8080

# Start application
CMD ["./start.sh"]
