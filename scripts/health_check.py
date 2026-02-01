#!/usr/bin/env python3
"""
Health Check Script

Quick health check for the scraping system.
Checks: Python, Dependencies, Elasticsearch, Redis, Storage.

Usage:
    python scripts/health_check.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def check_python():
    """Check Python version."""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version.major < 3 or (version.major == 3 and version.minor < 10):
        print("  ⚠ Python 3.10+ recommended")
    return True


def check_dependencies():
    """Check required packages."""
    packages = [
        ("crawl4ai", "Crawl4AI"),
        ("aiohttp", "aiohttp"),
        ("bs4", "BeautifulSoup"),
        ("elasticsearch", "Elasticsearch"),
        ("redis", "Redis"),
        ("dotenv", "python-dotenv"),
    ]
    
    all_ok = True
    for module, name in packages:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name} - NOT INSTALLED")
            all_ok = False
    
    return all_ok


def check_config():
    """Check configuration."""
    try:
        from config import get_environment, get_data_path, get_log_path
        
        env = get_environment()
        print(f"✓ Environment: {env.value}")
        print(f"✓ Data path: {get_data_path()}")
        print(f"✓ Log path: {get_log_path()}")
        return True
    except Exception as e:
        print(f"✗ Configuration error: {e}")
        return False


def check_elasticsearch():
    """Check Elasticsearch connection."""
    try:
        from config import get_elasticsearch_config
        from elasticsearch import Elasticsearch
        
        config = get_elasticsearch_config()
        if not config.is_configured:
            print("⚠ Elasticsearch not configured (password missing)")
            return True
        
        es = Elasticsearch(
            [config.host],
            basic_auth=(config.username, config.password),
            verify_certs=config.verify_certs,
        )
        
        if es.ping():
            info = es.info()
            print(f"✓ Elasticsearch: {config.host} (v{info['version']['number']})")
            return True
        else:
            print(f"✗ Elasticsearch ping failed: {config.host}")
            return False
            
    except ImportError:
        print("⚠ Elasticsearch package not installed")
        return True
    except Exception as e:
        print(f"✗ Elasticsearch error: {e}")
        return False


def check_redis():
    """Check Redis connection."""
    try:
        from config import get_redis_config
        import redis
        
        config = get_redis_config()
        r = redis.Redis(
            host=config.host,
            port=config.port,
            password=config.password or None,
            db=config.db,
        )
        
        if r.ping():
            print(f"✓ Redis: {config.host}:{config.port}")
            return True
        else:
            print(f"✗ Redis ping failed")
            return False
            
    except ImportError:
        print("⚠ Redis package not installed")
        return True
    except Exception as e:
        print(f"⚠ Redis not available: {e}")
        return True  # Redis is optional


def check_browser():
    """Check Crawl4AI browser."""
    try:
        from crawl4ai import AsyncWebCrawler
        print("✓ Crawl4AI available")
        
        # Check if browser is installed
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browsers = p.chromium.executable_path
            print(f"✓ Chromium: {browsers[:50]}...")
        
        return True
    except Exception as e:
        print(f"⚠ Browser check failed: {e}")
        print("  Run: crawl4ai-setup")
        return False


def check_directories():
    """Check required directories exist."""
    dirs = [
        Path("data"),
        Path("logs"),
        Path("junk_test"),
    ]
    
    all_ok = True
    for d in dirs:
        if d.exists():
            print(f"✓ Directory: {d}")
        else:
            d.mkdir(parents=True, exist_ok=True)
            print(f"✓ Created: {d}")
    
    return all_ok


def main():
    """Run all health checks."""
    print("\n" + "="*50)
    print("KLOUFI-SCRAPE HEALTH CHECK")
    print("="*50 + "\n")
    
    checks = [
        ("Python", check_python),
        ("Dependencies", check_dependencies),
        ("Configuration", check_config),
        ("Directories", check_directories),
        ("Elasticsearch", check_elasticsearch),
        ("Redis", check_redis),
        ("Browser", check_browser),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n[{name}]")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ Error: {e}")
            results.append((name, False))
    
    print("\n" + "="*50)
    print("SUMMARY")
    print("="*50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
    
    print(f"\n{passed}/{total} checks passed")
    
    if passed == total:
        print("\n🎉 System ready!")
        return 0
    else:
        print("\n⚠ Some checks failed. Review above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
