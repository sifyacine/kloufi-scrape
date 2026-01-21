# Ubuntu 24 LTS Deployment Guide

This document explains how to set up the `kloufi-scrape` project on a fresh Ubuntu 24.04 LTS server using the provided automation script.

## 🚀 One-Step Setup (Recommended)

The project includes a `setup.sh` script that automates the entire process:
- Installs system dependencies (Python, Git, Build tools, etc.)
- Creates a virtual environment and installs Python requirements
- Installs Playwright browser engines for `Crawl4AI`
- **Fixes hardcoded paths** in the existing `.sh` and `.py` files automatically.

### Running the Setup
```bash
# 1. Navigate to the project folder
cd ~/kloufi-scrape

# 2. Make the script executable
chmod +x setup.sh

# 3. Run the script
./setup.sh
```

---

## 🛠️ What the Setup Does

### 1. System Packages
Installs essential libraries for Python and scraper dependencies (like `lxml` and `Crawl4AI`).
```bash
sudo apt install -y python3-pip python3-venv build-essential libssl-dev libffi-dev \
    python3-dev libxml2-dev libxslt1-dev zlib1g-dev git
```

### 2. Browser Engines
The scrapers rely on `Crawl4AI`, which uses Playwright. The setup script runs:
```bash
playwright install --with-deps chromium
```

### 3. Path Normalization
The project scripts originally contained hardcoded paths to `/home/joaquim/kloufi-scrap`. The setup script automatically detects your current directory and updates all files using `sed`.

---

## 🏃 Running the Scrapers

After setup, always activate the virtual environment first:
```bash
source .venv/bin/activate
```

### Option A: Run via Shell Scripts (Recommended for Automation)
```bash
# Run all scrapers sequentially
./sh/crawl-all_opt.sh

# Run specific categories
./sh/crawl-immobilier.sh
./sh/crawl-voiture.sh
```

### Option B: Run via Python Directly
```bash
python3 scraper/main.py
```

## 📝 Maintenance
To regenerate the `requirements.txt` if you add new packages:
```bash
pip freeze > requirements.txt
```
