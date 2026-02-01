"""
Kloufi-Scrape Configuration Module

Centralized configuration for all scraping operations.
Supports both local testing and production deployment.
"""

import os
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import json

# ============================================================================
# ENVIRONMENT DETECTION
# ============================================================================

class Environment(Enum):
    LOCAL = "local"
    PRODUCTION = "production"
    DOCKER = "docker"


def get_environment() -> Environment:
    """Detect current environment based on ENV variable."""
    env = os.getenv("KLOUFI_ENV", "local").lower()
    if env == "production":
        return Environment.PRODUCTION
    elif env == "docker":
        return Environment.DOCKER
    return Environment.LOCAL


# ============================================================================
# PATH CONFIGURATION
# ============================================================================

# Project root (3 levels up from config/settings.py)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

# Environment-specific paths
PATHS = {
    Environment.LOCAL: {
        "data": PROJECT_ROOT / "junk_test",  # Local testing saves to junk_test
        "logs": PROJECT_ROOT / "logs",
        "proxy_scores": PROJECT_ROOT / "data" / "proxy_scores.json",
    },
    Environment.PRODUCTION: {
        "data": PROJECT_ROOT / "data" / "scraped",
        "logs": PROJECT_ROOT / "logs",
        "proxy_scores": PROJECT_ROOT / "data" / "proxy_scores.json",
    },
    Environment.DOCKER: {
        "data": Path("/app/data/scraped"),
        "logs": Path("/app/logs"),
        "proxy_scores": Path("/app/data/proxy_scores.json"),
    },
}


def get_data_path() -> Path:
    """Get the data output path for current environment."""
    env = get_environment()
    path = PATHS[env]["data"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    """Get the log path for current environment."""
    env = get_environment()
    path = PATHS[env]["logs"]
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_proxy_scores_path() -> Path:
    """Get the proxy scores file path."""
    env = get_environment()
    path = PATHS[env]["proxy_scores"]
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


# ============================================================================
# CATEGORIES CONFIGURATION
# ============================================================================

CATEGORIES = ["immobilier", "voiture", "emploi", "electromenager", "multimedia"]

# Category-specific Elasticsearch indices
ES_INDICES = {
    "immobilier": "immobilier",
    "voiture": "voiture",
    "emploi": "emploi",
    "electromenager": "electromenager",
    "multimedia": "multimedia",
}


# ============================================================================
# SCRAPER CONFIGURATION
# ============================================================================

@dataclass
class ScraperConfig:
    """Configuration for scraper behavior."""
    
    # Concurrency settings
    max_concurrent_listing: int = 2
    max_concurrent_details: int = 10
    batch_size: int = 10
    delay_between_batches: float = 5.0
    
    # Retry settings
    max_retries: int = 5
    retry_delay: float = 2.0
    
    # Timeout settings (milliseconds)
    page_timeout: int = 60000
    
    # Browser settings
    headless: bool = True
    
    # Proxy settings
    use_proxies: bool = True
    proxy_rotation_on_fail: bool = True
    
    # Storage settings
    save_to_elasticsearch: bool = True
    save_to_json: bool = False  # For local testing, can save to JSON
    
    @classmethod
    def for_local_testing(cls) -> "ScraperConfig":
        """Config optimized for local testing."""
        return cls(
            max_concurrent_listing=1,
            max_concurrent_details=3,
            batch_size=2,
            save_to_elasticsearch=False,
            save_to_json=True,
            headless=True,
        )
    
    @classmethod
    def for_production(cls) -> "ScraperConfig":
        """Config optimized for production."""
        return cls(
            max_concurrent_listing=2,
            max_concurrent_details=15,
            batch_size=10,
            save_to_elasticsearch=True,
            save_to_json=False,
            headless=True,
        )


def get_scraper_config() -> ScraperConfig:
    """Get scraper config based on environment."""
    env = get_environment()
    if env == Environment.LOCAL:
        return ScraperConfig.for_local_testing()
    return ScraperConfig.for_production()


# ============================================================================
# ELASTICSEARCH CONFIGURATION
# ============================================================================

@dataclass
class ElasticsearchConfig:
    """Elasticsearch connection configuration."""
    
    host: str = field(default_factory=lambda: os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200"))
    username: str = field(default_factory=lambda: os.getenv("ELASTICSEARCH_USERNAME", "elastic"))
    password: str = field(default_factory=lambda: os.getenv("ELASTICSEARCH_PASSWORD", ""))
    verify_certs: bool = field(default_factory=lambda: os.getenv("ELASTICSEARCH_VERIFY_CERTS", "false").lower() == "true")
    
    @property
    def is_configured(self) -> bool:
        """Check if Elasticsearch is properly configured."""
        return bool(self.host and self.password)


def get_elasticsearch_config() -> ElasticsearchConfig:
    """Get Elasticsearch configuration."""
    return ElasticsearchConfig()


# ============================================================================
# ALERTING CONFIGURATION
# ============================================================================

@dataclass
class AlertConfig:
    """Alerting and notification configuration."""
    
    # Telegram alerts
    telegram_enabled: bool = field(default_factory=lambda: bool(os.getenv("TELEGRAM_BOT_TOKEN")))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    
    # Email alerts (optional)
    email_enabled: bool = field(default_factory=lambda: bool(os.getenv("SMTP_HOST")))
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", ""))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    alert_email: str = field(default_factory=lambda: os.getenv("ALERT_EMAIL", ""))
    
    # Alert thresholds
    error_threshold: int = 10  # Alert after this many consecutive errors
    block_threshold: int = 5   # Alert after this many blocks detected
    captcha_threshold: int = 3 # Alert after this many captchas detected


def get_alert_config() -> AlertConfig:
    """Get alerting configuration."""
    return AlertConfig()


# ============================================================================
# SCHEDULING CONFIGURATION  
# ============================================================================

@dataclass
class ScheduleConfig:
    """Scraping schedule configuration."""
    
    # Run continuously (daemon mode)
    continuous_mode: bool = field(default_factory=lambda: os.getenv("CONTINUOUS_MODE", "true").lower() == "true")
    
    # Delay between full scrape cycles (seconds)
    cycle_delay: int = field(default_factory=lambda: int(os.getenv("CYCLE_DELAY", "3600")))  # 1 hour default
    
    # Category-specific delays (seconds) - to stagger requests
    category_delays: Dict[str, int] = field(default_factory=lambda: {
        "immobilier": 0,
        "voiture": 300,      # 5 min delay
        "emploi": 600,       # 10 min delay
        "electromenager": 900,  # 15 min delay
        "multimedia": 1200,     # 20 min delay
    })
    
    # Max runtime per category (seconds) before moving to next
    max_category_runtime: int = field(default_factory=lambda: int(os.getenv("MAX_CATEGORY_RUNTIME", "7200")))  # 2 hours


def get_schedule_config() -> ScheduleConfig:
    """Get scheduling configuration."""
    return ScheduleConfig()


# ============================================================================
# REDIS CONFIGURATION (for distributed state)
# ============================================================================

@dataclass
class RedisConfig:
    """Redis configuration for distributed state management."""
    
    host: str = field(default_factory=lambda: os.getenv("REDIS_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.getenv("REDIS_PORT", "6379")))
    password: str = field(default_factory=lambda: os.getenv("REDIS_PASSWORD", ""))
    db: int = field(default_factory=lambda: int(os.getenv("REDIS_DB", "0")))
    
    @property
    def url(self) -> str:
        """Get Redis connection URL."""
        if self.password:
            return f"redis://:{self.password}@{self.host}:{self.port}/{self.db}"
        return f"redis://{self.host}:{self.port}/{self.db}"


def get_redis_config() -> RedisConfig:
    """Get Redis configuration."""
    return RedisConfig()


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# ============================================================================
# EXPORT CONFIG SUMMARY
# ============================================================================

def print_config_summary():
    """Print current configuration for debugging."""
    env = get_environment()
    print(f"\n{'='*60}")
    print(f"KLOUFI-SCRAPE CONFIGURATION")
    print(f"{'='*60}")
    print(f"Environment: {env.value}")
    print(f"Data Path: {get_data_path()}")
    print(f"Log Path: {get_log_path()}")
    print(f"Categories: {CATEGORIES}")
    
    scraper_cfg = get_scraper_config()
    print(f"\nScraper Config:")
    print(f"  - Max Concurrent Listing: {scraper_cfg.max_concurrent_listing}")
    print(f"  - Max Concurrent Details: {scraper_cfg.max_concurrent_details}")
    print(f"  - Save to Elasticsearch: {scraper_cfg.save_to_elasticsearch}")
    print(f"  - Save to JSON: {scraper_cfg.save_to_json}")
    
    es_cfg = get_elasticsearch_config()
    print(f"\nElasticsearch: {'Configured' if es_cfg.is_configured else 'Not Configured'}")
    
    alert_cfg = get_alert_config()
    print(f"\nAlerts:")
    print(f"  - Telegram: {'Enabled' if alert_cfg.telegram_enabled else 'Disabled'}")
    print(f"  - Email: {'Enabled' if alert_cfg.email_enabled else 'Disabled'}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print_config_summary()
