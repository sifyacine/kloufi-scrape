# Dockerfile for kloufi-scrape
# Build argument: INSTALL_PLAYWRIGHT (default false). Set to "true" to install Playwright and browsers.

FROM python:3.13-slim

ARG INSTALL_PLAYWRIGHT=false
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system deps commonly needed by scraping tools and optional browsers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl wget ca-certificates gnupg ffmpeg libnss3 libatk1.0-0 libxss1 libasound2 libcups2 libglib2.0-0 libgtk-3-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Optionally install Playwright and browsers (if you rely on Playwright-enabled features)
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
      pip install playwright tf-playwright-stealth || true; \
      python -m playwright install --with-deps; \
    fi

# Copy project files
COPY . /app

# Create a non-root user and give ownership of app
RUN useradd -m appuser && chown -R appuser /app
USER appuser

ENV PATH="/home/appuser/.local/bin:${PATH}"

# Default command - run the main scraper. You can override at runtime.
CMD ["python", "scraper/main.py"]
