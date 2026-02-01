"""
Kloufi-Scrape Category Runner

Generic runner that discovers and executes site scrapers for a category.
"""

import asyncio
import importlib
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_scraper_config, CATEGORIES, get_data_path, Environment, get_environment
from scraper.utils.logger import get_logger
from scraper.proxy.proxy_manager import ProxyManager

logger = get_logger("category_runner")


@dataclass
class SiteConfig:
    """Configuration for a single site scraper."""
    name: str
    category: str
    module_path: str
    enabled: bool = True
    priority: int = 0  # Higher = run first


class CategoryRunner:
    """
    Runs all site scrapers for a specific category.
    
    Discovers site modules in sites/{category}/ and runs them.
    """
    
    def __init__(self, category: str):
        if category not in CATEGORIES:
            raise ValueError(f"Unknown category: {category}")
        
        self.category = category
        self.sites: List[SiteConfig] = []
        self._discover_sites()
    
    def _discover_sites(self):
        """Discover available site scrapers for this category."""
        sites_dir = Path(__file__).parent.parent / "sites" / self.category
        
        if not sites_dir.exists():
            logger.warning(f"Sites directory not found: {sites_dir}")
            return
        
        for site_dir in sites_dir.iterdir():
            if not site_dir.is_dir():
                continue
            if site_dir.name.startswith("_"):
                continue
            
            # Check for main.py
            main_file = site_dir / "main.py"
            if main_file.exists():
                self.sites.append(SiteConfig(
                    name=site_dir.name,
                    category=self.category,
                    module_path=f"sites.{self.category}.{site_dir.name}.main",
                ))
        
        # Sort by priority
        self.sites.sort(key=lambda s: -s.priority)
        
        logger.info(f"Discovered {len(self.sites)} sites for {self.category}")
    
    async def run_site(
        self,
        site: SiteConfig,
        proxy_manager: Optional[ProxyManager],
        config: Any,
        shutdown_event: asyncio.Event,
    ) -> Dict[str, Any]:
        """Run a single site scraper."""
        logger.info(f"Starting site: {site.name}")
        
        items_scraped = 0
        errors = 0
        
        try:
            # Import the site module
            module = importlib.import_module(site.module_path)
            
            # Check for required function
            if hasattr(module, "run_scraper"):
                # New-style async scraper
                result = await module.run_scraper(
                    proxy_manager=proxy_manager,
                    config=config,
                    shutdown_event=shutdown_event,
                )
                items_scraped = result.get("items_scraped", 0)
                errors = result.get("errors", 0)
                
            elif hasattr(module, "main"):
                # Old-style main() function - wrap it
                if asyncio.iscoroutinefunction(module.main):
                    await module.main()
                else:
                    # Run sync function in executor
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, module.main)
                    
            else:
                logger.warning(f"Site {site.name} has no run_scraper or main function")
                errors = 1
                
        except Exception as e:
            logger.error(f"Error running site {site.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            errors = 1
        
        return {
            "site": site.name,
            "items_scraped": items_scraped,
            "errors": errors,
        }
    
    async def run(
        self,
        proxy_manager: Optional[ProxyManager] = None,
        config: Optional[Any] = None,
        shutdown_event: Optional[asyncio.Event] = None,
        sites: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Run all (or specified) site scrapers for this category.
        
        Args:
            proxy_manager: Shared proxy manager
            config: Scraper configuration
            shutdown_event: Event to signal shutdown
            sites: Optional list of specific sites to run
            
        Returns:
            Dict with aggregated results
        """
        if config is None:
            config = get_scraper_config()
        
        if shutdown_event is None:
            shutdown_event = asyncio.Event()
        
        # Filter sites if specified
        sites_to_run = self.sites
        if sites:
            sites_to_run = [s for s in self.sites if s.name in sites]
        
        if not sites_to_run:
            logger.warning(f"No sites to run for {self.category}")
            return {"items_scraped": 0, "errors": 0}
        
        total_items = 0
        total_errors = 0
        site_results = []
        
        for site in sites_to_run:
            if shutdown_event.is_set():
                logger.info("Shutdown requested, stopping category run")
                break
            
            result = await self.run_site(
                site=site,
                proxy_manager=proxy_manager,
                config=config,
                shutdown_event=shutdown_event,
            )
            
            site_results.append(result)
            total_items += result.get("items_scraped", 0)
            total_errors += result.get("errors", 0)
            
            # Small delay between sites
            if not shutdown_event.is_set():
                await asyncio.sleep(2)
        
        return {
            "category": self.category,
            "items_scraped": total_items,
            "errors": total_errors,
            "sites": site_results,
        }


# Cache of runners
_runners: Dict[str, CategoryRunner] = {}


def get_runner(category: str) -> CategoryRunner:
    """Get or create a category runner."""
    if category not in _runners:
        _runners[category] = CategoryRunner(category)
    return _runners[category]


# ============================================================================
# CLI ENTRY POINT
# ============================================================================

async def main():
    """Test category runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run category scraper")
    parser.add_argument("category", choices=CATEGORIES)
    parser.add_argument("--sites", nargs="+", help="Specific sites to run")
    args = parser.parse_args()
    
    runner = get_runner(args.category)
    
    print(f"Sites for {args.category}:")
    for site in runner.sites:
        print(f"  - {site.name}")
    
    result = await runner.run(sites=args.sites)
    print(f"\nResult: {result}")


if __name__ == "__main__":
    asyncio.run(main())
