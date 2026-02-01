"""
Kloufi-Scrape Site Wrapper

Provides utilities to wrap existing site scrapers to work with 
the new dispatcher/storage system.
"""

import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.storage import get_storage, DataStorage
from core.alerting import get_alert_manager
from scraper.utils.logger import get_logger
from scraper.proxy.proxy_manager import ProxyManager


class SiteScraperWrapper:
    """
    Wrapper class to adapt existing site scrapers to the new system.
    
    Provides:
    - Unified storage (JSON for local, ES for production)
    - Automatic alerting integration
    - Progress tracking
    - Graceful shutdown support
    """
    
    def __init__(
        self,
        category: str,
        site_name: str,
        proxy_manager: Optional[ProxyManager] = None,
        config: Optional[Any] = None,
        shutdown_event: Optional[asyncio.Event] = None,
    ):
        self.category = category
        self.site_name = site_name
        self.proxy_manager = proxy_manager
        self.config = config
        self.shutdown_event = shutdown_event or asyncio.Event()
        
        self.storage = get_storage(category, site_name)
        self.alert_manager = get_alert_manager()
        self.logger = get_logger(f"{category}.{site_name}")
        
        # Stats
        self.items_scraped = 0
        self.errors = 0
    
    @property
    def should_stop(self) -> bool:
        """Check if shutdown was requested."""
        return self.shutdown_event.is_set()
    
    def get_proxy(self, domain: str) -> Optional[str]:
        """Get a proxy for the given domain."""
        if self.proxy_manager:
            try:
                return self.proxy_manager.get_proxy(domain)
            except Exception:
                return None
        return None
    
    def report_proxy_success(self, proxy: str, latency: float = 1.0):
        """Report successful proxy use."""
        if self.proxy_manager and proxy:
            self.proxy_manager.report_success(proxy, latency)
    
    def report_proxy_failure(self, proxy: str):
        """Report proxy failure."""
        if self.proxy_manager and proxy:
            self.proxy_manager.report_failure(proxy)
    
    async def save(self, data: Dict[str, Any]) -> bool:
        """
        Save scraped data using unified storage.
        
        Automatically handles JSON vs Elasticsearch based on environment.
        """
        success = self.storage.save(data)
        
        if success:
            self.items_scraped += 1
            await self.alert_manager.on_scrape_success(
                self.category, 
                data.get("url", ""),
                data
            )
        else:
            self.errors += 1
            await self.alert_manager.on_scrape_error(
                self.category,
                data.get("url", ""),
                "Storage save failed"
            )
        
        return success
    
    async def report_error(self, url: str, error: str):
        """Report a scraping error."""
        self.errors += 1
        self.logger.error(f"Error scraping {url}: {error}")
        await self.alert_manager.on_scrape_error(self.category, url, error)
    
    async def report_block(self, url: str, block_type: str = "block"):
        """Report a block or captcha detection."""
        self.logger.warning(f"Block detected ({block_type}): {url}")
        await self.alert_manager.on_block_detected(self.category, url, block_type)
    
    def get_results(self) -> Dict[str, Any]:
        """Get scraping results summary."""
        return {
            "category": self.category,
            "site": self.site_name,
            "items_scraped": self.items_scraped,
            "errors": self.errors,
            "storage_stats": self.storage.stats,
        }


def create_run_scraper(
    category: str,
    site_name: str,
    scrape_func: Callable,
):
    """
    Factory function to create a run_scraper function for existing scrapers.
    
    Usage:
        # In your existing main.py, add at the end:
        
        from core.site_wrapper import create_run_scraper
        
        async def _scrape_logic(wrapper):
            # Your existing scraping logic
            # Use wrapper.save(data) instead of insert_data_to_es
            # Check wrapper.should_stop periodically
            pass
        
        run_scraper = create_run_scraper("immobilier", "ouedkniss", _scrape_logic)
    """
    async def run_scraper(
        proxy_manager: Optional[ProxyManager] = None,
        config: Optional[Any] = None,
        shutdown_event: Optional[asyncio.Event] = None,
    ) -> Dict[str, Any]:
        wrapper = SiteScraperWrapper(
            category=category,
            site_name=site_name,
            proxy_manager=proxy_manager,
            config=config,
            shutdown_event=shutdown_event,
        )
        
        try:
            await scrape_func(wrapper)
        except Exception as e:
            wrapper.logger.error(f"Scraper error: {e}")
            import traceback
            wrapper.logger.error(traceback.format_exc())
            wrapper.errors += 1
        
        return wrapper.get_results()
    
    return run_scraper


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

async def example_scraper(wrapper: SiteScraperWrapper):
    """Example of how to use the wrapper in an existing scraper."""
    
    urls = ["https://example.com/listing1", "https://example.com/listing2"]
    
    for url in urls:
        # Check for shutdown
        if wrapper.should_stop:
            wrapper.logger.info("Shutdown requested, stopping")
            break
        
        # Get proxy
        proxy = wrapper.get_proxy("example.com")
        
        try:
            # Your scraping logic here
            data = {
                "titre": "Example Listing",
                "url": url,
                "prix": "1000000",
            }
            
            # Save using wrapper (handles JSON vs ES automatically)
            await wrapper.save(data)
            
            # Report proxy success
            wrapper.report_proxy_success(proxy)
            
        except Exception as e:
            # Report error
            await wrapper.report_error(url, str(e))
            wrapper.report_proxy_failure(proxy)


if __name__ == "__main__":
    # Test the wrapper
    async def test():
        wrapper = SiteScraperWrapper("immobilier", "test")
        await example_scraper(wrapper)
        print(wrapper.get_results())
    
    asyncio.run(test())
