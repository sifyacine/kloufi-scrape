"""
Kloufi-Scrape Logger Module

Centralized logging with support for:
- Console output (colored)
- File rotation
- JSON formatting (for production)
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

# Try to import from config, fall back to defaults
try:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from config import get_log_path, LOG_LEVEL, LOG_FORMAT, LOG_DATE_FORMAT
except ImportError:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    def get_log_path():
        path = Path("logs")
        path.mkdir(exist_ok=True)
        return path


# Color codes for console output
class Colors:
    RESET = "\033[0m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BOLD = "\033[1m"


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to console output."""
    
    LEVEL_COLORS = {
        logging.DEBUG: Colors.CYAN,
        logging.INFO: Colors.GREEN,
        logging.WARNING: Colors.YELLOW,
        logging.ERROR: Colors.RED,
        logging.CRITICAL: Colors.RED + Colors.BOLD,
    }
    
    def format(self, record):
        # Add color to levelname
        color = self.LEVEL_COLORS.get(record.levelno, Colors.WHITE)
        record.levelname = f"{color}{record.levelname}{Colors.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Formatter that outputs JSON lines (for log aggregation)."""
    
    def format(self, record):
        import json
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        if hasattr(record, "category"):
            log_obj["category"] = record.category
        if hasattr(record, "site"):
            log_obj["site"] = record.site
        if hasattr(record, "url"):
            log_obj["url"] = record.url
            
        return json.dumps(log_obj)


# Cache of loggers
_loggers = {}


def get_logger(name: str, level: str = None) -> logging.Logger:
    """
    Get or create a logger with the specified name.
    
    Args:
        name: Logger name (usually module name)
        level: Optional log level override
        
    Returns:
        Configured logger instance
    """
    if name in _loggers:
        return _loggers[name]
    
    logger = logging.getLogger(name)
    
    # Set level
    log_level = level or LOG_LEVEL
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # Don't add handlers if already configured
    if logger.handlers:
        _loggers[name] = logger
        return logger
    
    # Create formatters
    console_formatter = ColoredFormatter(LOG_FORMAT, LOG_DATE_FORMAT)
    file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler with rotation
    try:
        log_dir = get_log_path()
        log_file = log_dir / "scraper.log"
        
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10_000_000,  # 10MB
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Separate error log
        error_file = log_dir / "errors.log"
        error_handler = RotatingFileHandler(
            error_file,
            maxBytes=5_000_000,  # 5MB
            backupCount=5,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(file_formatter)
        logger.addHandler(error_handler)
        
    except Exception as e:
        logger.warning(f"Could not setup file logging: {e}")
    
    # Prevent propagation to root logger
    logger.propagate = False
    
    _loggers[name] = logger
    return logger


def get_category_logger(category: str, site: str = None) -> logging.Logger:
    """
    Get a logger with category context.
    
    Args:
        category: Category name
        site: Optional site name
        
    Returns:
        Logger with category context
    """
    name = f"{category}.{site}" if site else category
    logger = get_logger(name)
    
    # Add extra context
    class CategoryAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            kwargs.setdefault("extra", {})
            kwargs["extra"]["category"] = self.extra.get("category")
            kwargs["extra"]["site"] = self.extra.get("site")
            return msg, kwargs
    
    return CategoryAdapter(logger, {"category": category, "site": site})


# Convenience function for quick logging
def log_scrape(category: str, site: str, url: str, success: bool, message: str = ""):
    """Log a scrape event with context."""
    logger = get_category_logger(category, site)
    
    status = "✓" if success else "✗"
    level = logging.INFO if success else logging.WARNING
    
    logger.log(level, f"[{status}] {url} - {message}", extra={"url": url})


if __name__ == "__main__":
    # Test logging
    logger = get_logger("test")
    logger.debug("Debug message")
    logger.info("Info message")
    logger.warning("Warning message")
    logger.error("Error message")
    logger.critical("Critical message")
    
    cat_logger = get_category_logger("immobilier", "ouedkniss")
    cat_logger.info("Category-specific log")
    
    log_scrape("voiture", "tonobiles", "https://example.com", True, "Scraped successfully")