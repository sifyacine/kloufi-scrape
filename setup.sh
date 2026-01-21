#!/bash/sh

# Kloufi-Scrape Automation Setup Script for Ubuntu 24 LTS
# This script automates system dependencies, virtual environment setup, 
# library installation, and path fixing.

set -e # Exit immediately if a command exits with a non-zero status

echo "🚀 Starting setup for kloufi-scrape..."

# 1. Update system and install dependencies
echo "📦 Installing system packages..."
sudo apt update
sudo apt install -y python3-pip python3-venv build-essential libssl-dev libffi-dev \
    python3-dev libxml2-dev libxslt1-dev zlib1g-dev git

# 2. Create and activate virtual environment
echo "🛠️ Setting up virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# 3. Install Python dependencies
echo "🐍 Installing Python libraries (this may take a minute)..."
pip install --upgrade pip
pip install -r requirements.txt

# 4. Install Playwright browsers (Required for Crawl4AI)
echo "🌐 Installing browser engines..."
playwright install --with-deps chromium

# 5. Fix hardcoded absolute paths
echo "🛠️ Fixing hardcoded paths in scripts..."
OLD_PATH="/home/joaquim/kloufi-scrap"
NEW_PATH=$(pwd)

# Replace the old path with the current directory in all .sh and .py files
grep -rli "$OLD_PATH" . | xargs -i@ sed -i "s|$OLD_PATH|$NEW_PATH|g"

# 6. Make shell scripts executable
echo "📂 Setting permissions for shell scripts..."
chmod +x sh/*.sh 2>/dev/null || true
chmod -R +x sh/**/*.sh 2>/dev/null || true

echo "✅ Setup complete!"
echo "--------------------------------------------------------"
echo "To start, run:"
echo "source .venv/bin/activate"
echo "python3 scraper/main.py"
echo "--------------------------------------------------------"
