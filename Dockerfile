# ====================================================================
# AVT - FLOWER MERCHANT & COMMISSION AGENT
# Production Container Image
# ====================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_DEBUG=False

# Install system dependencies for Pillow and ReportLab
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libjpeg-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy application source
COPY . /app/

# Collect static files with WhiteNoise
RUN python manage.py collectstatic --noinput

# Create directory for persistent SQLite data
RUN mkdir -p /app/data

# Expose server port
EXPOSE 8000

# Container Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/health/ || exit 1

# Launch production WSGI server
CMD ["gunicorn", "--config", "gunicorn.conf.py", "config.wsgi:application"]
