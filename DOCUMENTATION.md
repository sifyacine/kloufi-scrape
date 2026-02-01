# Kloufi-Scrape Documentation

## 📋 Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Configuration](#configuration)
5. [Local Testing](#local-testing)
6. [Production Deployment](#production-deployment)
7. [Docker Deployment](#docker-deployment)
8. [Monitoring & Alerts](#monitoring--alerts)
9. [Scraper Development](#scraper-development)
10. [Troubleshooting](#troubleshooting)

---

## 📌 Project Overview

Kloufi-Scrape is a production-ready web scraping system designed for continuous, automated data collection from Algerian websites across 5 categories:

| Category | Description | Sites |
|----------|-------------|-------|
| **immobilier** | Real Estate | OuedKniss, Krello, Lkeria, Beytic, etc. |
| **voiture** | Vehicles | OuedKniss, Tonobiles, AutoBessah, etc. |
| **emploi** | Jobs | Emploitic, AlgerieJob, CVYA, etc. |
| **electromenager** | Home Appliances | Jumia, Starmania, WebStar, etc. |
| **multimedia** | Electronics | Jumia, Informatics, etc. |

### Key Features

- ✅ **Continuous Auto-Scraping** - Runs 24/7 until manually stopped
- ✅ **Smart Proxy Rotation** - Avoids blocks with intelligent proxy management
- ✅ **Dual Storage** - Elasticsearch (production) & JSON (testing)
- ✅ **Real-time Alerts** - Telegram/Email notifications for issues
- ✅ **Docker Support** - Easy deployment with docker-compose
- ✅ **Graceful Shutdown** - Clean stop with data preservation

---

## 🏗 Architecture

```
kloufi-scrape/
├── config/                    # Centralized configuration
│   ├── __init__.py
│   └── settings.py           # All config in one place
│
├── core/                      # Core orchestration
│   ├── __init__.py
│   ├── dispatcher.py         # Main scraping orchestrator
│   ├── category_runner.py    # Runs all sites for a category
│   ├── alerting.py           # Telegram/Email alerts
│   └── storage.py            # Unified data storage
│
├── scraper/                   # Scraping infrastructure
│   ├── main.py               # Legacy entry point
│   ├── browser/              # Browser fingerprinting
│   │   ├── fingerprint.py
│   │   ├── stealth.py
│   │   └── user_agents.py
│   ├── crawler/              # Crawl4AI integration
│   │   ├── crawler_runner.py
│   │   └── fallback_proxyium.py
│   ├── detection/            # Block/captcha detection
│   │   ├── block_detector.py
│   │   └── captcha_detector.py
│   ├── proxy/                # Proxy management
│   │   ├── proxy_manager.py
│   │   ├── proxy_scoring.py
│   │   └── proxy_sources.py
│   └── utils/                # Utilities
│       ├── logger.py
│       └── storage.py
│
├── sites/                     # Site-specific scrapers
│   ├── immobilier/
│   │   ├── ouedkniss/
│   │   │   ├── main.py       # Listing scraper
│   │   │   └── scrape_details.py
│   │   ├── krello/
│   │   └── ...
│   ├── voiture/
│   ├── emploi/
│   ├── electromenager/
│   └── multimedia/
│
├── utils/                     # Category-specific utilities
│   ├── immobilier.py         # Real estate normalization
│   ├── voiture.py            # Vehicle normalization
│   ├── emploi.py             # Job normalization
│   └── ...
│
├── insert2db/                 # Elasticsearch integration
│   └── insert_scrape.py
│
├── scripts/                   # Deployment & testing scripts
│   ├── deploy.sh             # Production deployment
│   └── local_test.py         # Local testing runner
│
├── docker/                    # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── data/                      # Scraped data (production)
├── logs/                      # Log files
├── junk_test/                 # Local test output (gitignored)
│
├── .env.example              # Environment template
├── requirements.txt          # Python dependencies
└── DOCUMENTATION.md          # This file
```

### Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         DISPATCHER                               │
│                    (core/dispatcher.py)                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┬───────────────┐
         ▼               ▼               ▼               ▼
    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
    │immobilier│    │ voiture │    │ emploi  │    │   ...   │
    └────┬────┘    └────┬────┘    └────┬────┘    └────┬────┘
         │              │              │              │
    ┌────┴────┐    ┌────┴────┐    ┌────┴────┐        │
    │Category │    │Category │    │Category │        │
    │ Runner  │    │ Runner  │    │ Runner  │        │
    └────┬────┘    └────┬────┘    └────┬────┘        │
         │              │              │              │
   ┌─────┴─────┐  ┌─────┴─────┐       │              │
   │ OuedKniss │  │ Tonobiles │       │              │
   │  Krello   │  │  CardiaS  │       │              │
   │   ...     │  │    ...    │       │              │
   └─────┬─────┘  └─────┬─────┘       │              │
         │              │              │              │
         └──────────────┴──────────────┴──────────────┘
                         │
                    ┌────┴────┐
                    │ STORAGE │
                    │(core/)  │
                    └────┬────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
    ┌─────────┐                    ┌─────────┐
    │  JSON   │ (Local Testing)   │Elastic- │ (Production)
    │  Files  │                   │ search  │
    └─────────┘                    └─────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose (for containerized deployment)
- Elasticsearch 8.x (for production data storage)

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd kloufi-scrape

# Create virtual environment
python -m venv .venv

# Activate (Linux/Mac)
source .venv/bin/activate

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Setup Crawl4AI browser
crawl4ai-setup

# Copy environment template
cp .env.example .env
# Edit .env with your settings
```

### Run Locally (Testing)

```bash
# Set local environment
export KLOUFI_ENV=local  # Linux/Mac
$env:KLOUFI_ENV="local"  # Windows PowerShell

# Run with local testing script
python scripts/local_test.py --category immobilier

# Or run dispatcher directly
python core/dispatcher.py --single-run --categories immobilier
```

### Run in Production

```bash
# Set production environment
export KLOUFI_ENV=production

# Run dispatcher (continuous mode)
python core/dispatcher.py
```

---

## ⚙️ Configuration

All configuration is centralized in `config/settings.py`. Settings can be overridden via environment variables.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KLOUFI_ENV` | `local` | Environment: `local`, `production`, `docker` |
| `ELASTICSEARCH_HOST` | `http://localhost:9200` | Elasticsearch URL |
| `ELASTICSEARCH_USERNAME` | `elastic` | ES username |
| `ELASTICSEARCH_PASSWORD` | - | ES password |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `TELEGRAM_BOT_TOKEN` | - | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | - | Telegram chat ID for alerts |
| `CONTINUOUS_MODE` | `true` | Run continuously or single-run |
| `CYCLE_DELAY` | `3600` | Seconds between scrape cycles |
| `MAX_CONCURRENT_LISTING` | `2` | Concurrent listing page scrapers |
| `MAX_CONCURRENT_DETAILS` | `15` | Concurrent detail page scrapers |

### Environment Modes

| Mode | Data Storage | Concurrency | Use Case |
|------|-------------|-------------|----------|
| `local` | JSON in `junk_test/` | Low (1-3) | Development & testing |
| `production` | Elasticsearch | High (10-15) | Live deployment |
| `docker` | Elasticsearch | High (10-15) | Containerized deployment |

---

## 🧪 Local Testing

Local testing mode saves data to `junk_test/` (which is gitignored) instead of Elasticsearch.

### Run Tests

```bash
# Test single category
python scripts/local_test.py --category immobilier

# Test specific site (not yet implemented in runner)
python scripts/local_test.py --category voiture

# Test with continuous mode (keep running)
python scripts/local_test.py --category emploi --continuous
```

### View Test Output

```bash
# List scraped files
ls -la junk_test/immobilier/

# View a scraped item
cat junk_test/immobilier/ouedkniss/*.json | head -100
```

### Test Configuration

Local mode automatically:
- Reduces concurrency (fewer parallel requests)
- Saves to JSON files instead of Elasticsearch
- Enables more verbose logging

---

## 🖥 Production Deployment

### Option 1: Systemd Service (Recommended)

```bash
# Run deployment script
sudo ./scripts/deploy.sh

# Configure
sudo nano /opt/kloufi-scrape/.env

# Start service
sudo systemctl start kloufi-scraper

# Enable on boot
sudo systemctl enable kloufi-scraper

# View logs
sudo journalctl -u kloufi-scraper -f
```

### Option 2: Manual Setup

```bash
# Create directory
sudo mkdir -p /opt/kloufi-scrape
sudo cp -r . /opt/kloufi-scrape/

# Setup virtual environment
cd /opt/kloufi-scrape
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
crawl4ai-setup

# Configure
cp .env.example .env
nano .env  # Add your settings

# Run with screen/tmux
screen -S kloufi
export KLOUFI_ENV=production
python core/dispatcher.py
# Ctrl+A, D to detach
```

### Elasticsearch Setup

```bash
# Install Elasticsearch
wget https://artifacts.elastic.co/downloads/elasticsearch/elasticsearch-8.11.0-amd64.deb
sudo dpkg -i elasticsearch-8.11.0-amd64.deb

# Configure
sudo nano /etc/elasticsearch/elasticsearch.yml
# Set: network.host: 0.0.0.0
# Set: discovery.type: single-node

# Start
sudo systemctl start elasticsearch
sudo systemctl enable elasticsearch

# Get password
sudo /usr/share/elasticsearch/bin/elasticsearch-reset-password -u elastic
```

---

## 🐳 Docker Deployment

### Quick Start

```bash
cd docker

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f scraper

# Stop
docker-compose down
```

### Scrape Specific Categories

```bash
# Only immobilier and voiture
CATEGORIES="immobilier voiture" docker-compose up -d scraper
```

### With Monitoring Stack

```bash
# Start with Kibana, Prometheus, Grafana
docker-compose --profile monitoring up -d
```

### Services

| Service | Port | Description |
|---------|------|-------------|
| scraper | - | Main scraper container |
| redis | 6379 | Proxy scoring persistence |
| elasticsearch | 9200 | Data storage |
| kibana | 5601 | Data visualization (optional) |
| prometheus | 9090 | Metrics (optional) |
| grafana | 3000 | Dashboards (optional) |

---

## 📢 Monitoring & Alerts

### Telegram Alerts

1. Create a bot via [@BotFather](https://t.me/botfather)
2. Get your chat ID from [@userinfobot](https://t.me/userinfobot)
3. Add to `.env`:
   ```
   TELEGRAM_BOT_TOKEN=your_bot_token
   TELEGRAM_CHAT_ID=your_chat_id
   ```

### Alert Types

| Alert | Level | Trigger |
|-------|-------|---------|
| Startup | ℹ️ INFO | Scraper started |
| Progress | ℹ️ INFO | Every 100 items scraped |
| Category Complete | ✅ SUCCESS | Category finished |
| Cycle Complete | ✅ SUCCESS | Full cycle finished |
| High Errors | 🚨 ERROR | 10+ consecutive errors |
| Captcha Flood | ⚠️ WARNING | 3+ captchas detected |
| IP Block | ⚠️ WARNING | 5+ blocks detected |
| Shutdown | ℹ️ INFO | Scraper stopped |

### Health Check

```python
from core.alerting import get_alert_manager

manager = get_alert_manager()
health = await manager.health_check()
print(health)
```

---

## 👨‍💻 Scraper Development

### Adding a New Site

1. Create site directory:
   ```bash
   mkdir -p sites/immobilier/newsite
   ```

2. Create `main.py`:
   ```python
   # sites/immobilier/newsite/main.py
   import asyncio
   from core.storage import get_storage
   from scraper.proxy.proxy_manager import ProxyManager
   
   async def run_scraper(
       proxy_manager: ProxyManager = None,
       config = None,
       shutdown_event: asyncio.Event = None,
   ):
       storage = get_storage("immobilier", "newsite")
       items_scraped = 0
       errors = 0
       
       # Your scraping logic here
       # Use storage.save(data) to store items
       
       return {
           "items_scraped": items_scraped,
           "errors": errors,
       }
   ```

3. The dispatcher will auto-discover it on next run.

### Site Structure

```
sites/{category}/{site}/
├── main.py           # Entry point with run_scraper()
├── scrape_details.py # Detail page scraper
└── __pycache__/
```

### Using Crawl4AI

```python
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
from scraper.browser.fingerprint import build_context

config = CrawlerRunConfig(
    cache_mode=CacheMode.BYPASS,
    page_timeout=60000,
    wait_until="domcontentloaded",
    js_code=["window.scrollTo(0, document.body.scrollHeight);"],
    delay_before_return_html=3,
)

async with AsyncWebCrawler(
    proxy=proxy,
    browser_context=build_context(),
    headless=True,
) as crawler:
    result = await crawler.arun(url=url, config=config)
    if result.success:
        html = result.html
        # Parse with BeautifulSoup
```

---

## 🔧 Troubleshooting

### Common Issues

#### Browser Not Found
```bash
# Reinstall browsers
crawl4ai-setup
playwright install chromium --with-deps
```

#### Elasticsearch Connection Failed
```bash
# Check if running
curl -u elastic:password http://localhost:9200

# Check logs
sudo journalctl -u elasticsearch -f
```

#### High Memory Usage
```bash
# Reduce concurrency in .env
MAX_CONCURRENT_DETAILS=5
MAX_CONCURRENT_LISTING=1
```

#### Proxy Errors
```bash
# Clear proxy scores
rm data/proxy_scores.json
# Restart scraper
```

#### Captcha Flood
- Reduce concurrency
- Add longer delays between requests
- Consider using premium proxies

### Log Files

| Log | Location | Description |
|-----|----------|-------------|
| Main | `logs/scraper.log` | All scraping activity |
| Service | `logs/service.log` | Systemd service output |
| Errors | `logs/service-error.log` | Service errors |

### Debug Mode

```bash
# Enable debug logging
export LOG_LEVEL=DEBUG
python core/dispatcher.py --single-run
```

---

## 📄 License

[Your License Here]

## 🤝 Contributing

1. Fork the repository
2. Create your feature branch
3. Run local tests
4. Submit a pull request

---

*Last updated: February 2026*
