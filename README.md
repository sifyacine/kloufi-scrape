# 🕷️ Kloufi-Scrape

Production-ready web scraping system for continuous, automated data collection from Algerian websites.

## ✨ Features

- **5 Categories**: Immobilier, Voiture, Emploi, Electromenager, Multimedia
- **40+ Sites**: OuedKniss, Krello, Tonobiles, Emploitic, and more
- **Auto-Scraping**: Runs 24/7 with intelligent scheduling
- **Smart Proxies**: Automatic rotation with scoring system
- **Dual Storage**: Elasticsearch (production) + JSON (testing)
- **Real-time Alerts**: Telegram notifications for issues
- **Docker Ready**: One-command deployment

## 🚀 Quick Start

### Local Testing

```bash
# Setup
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows
source .venv/bin/activate      # Linux/Mac
pip install -r requirements.txt
crawl4ai-setup

# Configure
cp .env.example .env

# Run (saves to junk_test/)
$env:KLOUFI_ENV="local"
python scripts/local_test.py --category immobilier
```

### Production

```bash
# Configure
cp .env.example .env
nano .env  # Add Elasticsearch & Telegram settings

# Run
export KLOUFI_ENV=production
python core/dispatcher.py
```

### Docker

```bash
cd docker
docker-compose up -d
```

## 📁 Project Structure

```
kloufi-scrape/
├── config/           # Centralized configuration
├── core/             # Orchestration & storage
│   ├── dispatcher.py # Main auto-scraping controller
│   ├── alerting.py   # Telegram/Email alerts
│   └── storage.py    # Unified data storage
├── scraper/          # Scraping infrastructure
│   ├── proxy/        # Proxy management
│   ├── browser/      # Browser fingerprinting
│   └── detection/    # Block/captcha detection
├── sites/            # Category scrapers
│   ├── immobilier/   # Real estate sites
│   ├── voiture/      # Vehicle sites
│   ├── emploi/       # Job sites
│   └── ...
├── docker/           # Docker configuration
├── scripts/          # Deployment scripts
└── DOCUMENTATION.md  # Full documentation
```

## ⚙️ Configuration

| Environment | Data Storage | Use Case |
|-------------|--------------|----------|
| `local` | JSON files in `junk_test/` | Development |
| `production` | Elasticsearch | Live deployment |
| `docker` | Elasticsearch | Container deployment |

Set via `KLOUFI_ENV` environment variable.

## 📊 Monitoring

Configure Telegram alerts in `.env`:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

Receive alerts for:
- ✅ Scraping progress (every 100 items)
- ⚠️ Block/captcha detection
- 🚨 High error rates
- ℹ️ Startup/shutdown events

## 📖 Documentation

See [DOCUMENTATION.md](DOCUMENTATION.md) for complete documentation including:
- Architecture details
- Adding new scrapers
- Troubleshooting
- Production deployment guide

## 📝 License

[Your License]

---

*Built with [Crawl4AI](https://github.com/unclecode/crawl4ai)*

