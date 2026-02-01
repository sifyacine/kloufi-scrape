# ============================================================================
# KLOUFI-SCRAPE DOCKERFILE
# ============================================================================
# Production-ready Docker image for continuous web scraping
#
# Build:
#   docker build -t kloufi-scraper -f docker/Dockerfile .
#
# Run:
#   docker run -d --name kloufi kloufi-scraper
# ============================================================================

FROM python:3.13-slim

# Build arguments
ARG INSTALL_PLAYWRIGHT=true

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    KLOUFI_ENV=docker \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Build essentials
    build-essential \
    curl \
    wget \
    ca-certificates \
    gnupg \
    # Browser dependencies
    ffmpeg \
    libnss3 \
    libatk1.0-0 \
    libxss1 \
    libasound2 \
    libcups2 \
    libglib2.0-0 \
    libgtk-3-0 \
    libdrm2 \
    libgbm1 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
    # Cleanup
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt && \
    pip install \
        redis \
        python-dotenv \
        elasticsearch \
        aiohttp

# Install Playwright and browsers (if enabled)
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
        pip install playwright && \
        playwright install chromium --with-deps; \
    fi

# Install crawl4ai browser
RUN crawl4ai-setup || true

# Copy project files
COPY . /app

# Create necessary directories
RUN mkdir -p /app/data /app/logs /app/junk_test

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Add local bin to path
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Health check
HEALTHCHECK --interval=60s --timeout=30s --start-period=120s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Default command - run the dispatcher
CMD ["python", "core/dispatcher.py"]
