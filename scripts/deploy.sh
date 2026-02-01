#!/bin/bash
# ============================================================================
# KLOUFI-SCRAPE PRODUCTION DEPLOYMENT SCRIPT
# ============================================================================
# Deploys the scraper on Ubuntu VM for continuous operation
#
# Usage:
#   chmod +x scripts/deploy.sh
#   ./scripts/deploy.sh
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ============================================================================
# CONFIGURATION
# ============================================================================
INSTALL_DIR="${INSTALL_DIR:-/opt/kloufi-scrape}"
SERVICE_USER="${SERVICE_USER:-kloufi}"
# Auto-detect Python version (prefer 3.12, then 3.11, then default python3)
if command -v python3.12 &>/dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3.11 &>/dev/null; then
    PYTHON_CMD="python3.11"
else
    PYTHON_CMD="python3"
fi

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================
log_info "Starting Kloufi-Scrape deployment..."

# Check if running as root or with sudo
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root or with sudo"
    exit 1
fi

# ============================================================================
# SYSTEM DEPENDENCIES
# ============================================================================
log_info "Installing system dependencies..."

apt-get update
apt-get install -y \
    software-properties-common \
    curl \
    wget \
    git \
    build-essential \
    python3 \
    python3-venv \
    python3-dev \
    python3-pip \
    redis-server

# Browser dependencies for Playwright/Crawl4AI
apt-get install -y \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    libatspi2.0-0 \
    fonts-liberation

# ============================================================================
# CREATE SERVICE USER
# ============================================================================
log_info "Setting up service user..."

if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$SERVICE_USER"
    usermod -aG docker "$SERVICE_USER"
    log_info "Created user: $SERVICE_USER"
else
    log_info "User $SERVICE_USER already exists"
fi

# ============================================================================
# SETUP INSTALL DIRECTORY
# ============================================================================
log_info "Setting up installation directory..."

mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/data"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/junk_test"

# Copy project files (assumes running from project directory)
if [[ -f "requirements.txt" ]]; then
    cp -r . "$INSTALL_DIR/"
else
    log_error "Run this script from the kloufi-scrape project directory"
    exit 1
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# ============================================================================
# PYTHON VIRTUAL ENVIRONMENT
# ============================================================================
log_info "Setting up Python virtual environment..."
log_info "Using Python: $PYTHON_CMD"

sudo -u "$SERVICE_USER" bash << EOF
cd "$INSTALL_DIR"
$PYTHON_CMD -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# Install browser for Crawl4AI
crawl4ai-setup || true
playwright install chromium --with-deps || true
EOF

# ============================================================================
# ENVIRONMENT CONFIGURATION
# ============================================================================
log_info "Setting up environment configuration..."

if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    log_warn "Created .env from template. Please edit $INSTALL_DIR/.env with your settings!"
fi

# Set correct permissions for .env
chmod 600 "$INSTALL_DIR/.env"
chown "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/.env"

# ============================================================================
# SYSTEMD SERVICE
# ============================================================================
log_info "Creating systemd service..."

cat > /etc/systemd/system/kloufi-scraper.service << EOF
[Unit]
Description=Kloufi-Scrape Web Scraper
After=network.target redis.service elasticsearch.service
Wants=redis.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
Environment="PATH=$INSTALL_DIR/venv/bin:/usr/bin"
Environment="KLOUFI_ENV=production"
ExecStart=$INSTALL_DIR/venv/bin/python core/dispatcher.py
Restart=always
RestartSec=30

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$INSTALL_DIR/data $INSTALL_DIR/logs $INSTALL_DIR/junk_test

# Resource limits
MemoryMax=4G
CPUQuota=80%

# Logging
StandardOutput=append:$INSTALL_DIR/logs/service.log
StandardError=append:$INSTALL_DIR/logs/service-error.log

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# ============================================================================
# LOG ROTATION
# ============================================================================
log_info "Setting up log rotation..."

cat > /etc/logrotate.d/kloufi-scraper << EOF
$INSTALL_DIR/logs/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 640 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload kloufi-scraper > /dev/null 2>&1 || true
    endscript
}
EOF

# ============================================================================
# FINAL SETUP
# ============================================================================
log_info "Deployment complete!"

echo ""
echo "============================================================================"
echo "NEXT STEPS:"
echo "============================================================================"
echo ""
echo "1. Edit configuration:"
echo "   sudo nano $INSTALL_DIR/.env"
echo ""
echo "2. Start the service:"
echo "   sudo systemctl start kloufi-scraper"
echo ""
echo "3. Enable auto-start on boot:"
echo "   sudo systemctl enable kloufi-scraper"
echo ""
echo "4. View logs:"
echo "   sudo journalctl -u kloufi-scraper -f"
echo "   tail -f $INSTALL_DIR/logs/scraper.log"
echo ""
echo "5. Check status:"
echo "   sudo systemctl status kloufi-scraper"
echo ""
echo "============================================================================"
echo "FOR DOCKER DEPLOYMENT:"
echo "============================================================================"
echo ""
echo "   cd $INSTALL_DIR/docker"
echo "   docker-compose up -d"
echo ""
echo "============================================================================"
